"""Persistent ChromaDB retrieval for government scheme records."""

import hashlib
import json
from pathlib import Path
from typing import Any

from rag.embeddings import DEFAULT_MODEL_NAME, create_embeddings, load_embedding_model


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMES_PATH = PROJECT_ROOT / "data" / "schemes.json"
DEFAULT_PERSIST_DIRECTORY = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION_NAME = "government_schemes"
SEARCH_FIELDS = (
	"description",
	"category",
	"eligibility",
	"benefits",
	"documents",
	"required_documents",
	"application_process",
	"apply_url",
)


def _as_text(value: Any) -> str:
	if isinstance(value, list):
		return "; ".join(str(item) for item in value)
	if isinstance(value, dict):
		return json.dumps(value, ensure_ascii=False, sort_keys=True)
	return str(value)


def _scheme_name(scheme: dict[str, Any]) -> str:
	return scheme.get("scheme_name") or scheme.get("name") or scheme.get("id") or "Unknown Scheme"


def _scheme_document(scheme: dict[str, Any]) -> str:
	fields = [("Scheme", _scheme_name(scheme))]
	for field in SEARCH_FIELDS:
		if field in scheme and scheme[field] is not None:
			fields.append((field.replace("_", " ").title(), scheme[field]))
	return "\n".join(f"{label}: {_as_text(value)}" for label, value in fields)


def _scheme_id(scheme_name: str) -> str:
	digest = hashlib.sha256(scheme_name.encode("utf-8")).hexdigest()
	return f"scheme-{digest}"


class SchemeRetriever:
	"""Index scheme JSON in Chroma and retrieve complete scheme records."""

	def __init__(
		self,
		schemes_path: str | Path = DEFAULT_SCHEMES_PATH,
		persist_directory: str | Path = DEFAULT_PERSIST_DIRECTORY,
		collection_name: str = DEFAULT_COLLECTION_NAME,
		model_name: str = DEFAULT_MODEL_NAME,
		embedding_model: Any | None = None,
	) -> None:
		try:
			import chromadb
		except ImportError as exc:
			raise RuntimeError(
				"ChromaDB is not installed. Run: pip install -r requirements.txt"
			) from exc

		self.schemes = self._load_schemes(Path(schemes_path))
		self.schemes_by_id = {
			_scheme_id(_scheme_name(scheme)): scheme for scheme in self.schemes
		}
		self.embedding_model = embedding_model or load_embedding_model(model_name)
		client = chromadb.PersistentClient(path=str(persist_directory))
		self.collection = client.get_or_create_collection(
			name=collection_name,
			metadata={"hnsw:space": "cosine"},
		)
		self._sync_collection()

	@staticmethod
	def _load_schemes(schemes_path: Path) -> list[dict[str, Any]]:
		try:
			schemes = json.loads(schemes_path.read_text(encoding="utf-8"))
		except FileNotFoundError as exc:
			raise FileNotFoundError(f"Scheme data file not found: {schemes_path}") from exc
		except json.JSONDecodeError as exc:
			raise ValueError(f"Scheme data is not valid JSON: {schemes_path}") from exc

		if not isinstance(schemes, list):
			raise ValueError("Scheme data must be a JSON array.")

		names = set()
		for index, scheme in enumerate(schemes):
			if not isinstance(scheme, dict):
				raise ValueError(f"Scheme at index {index} must be a JSON object.")
			s_name = _scheme_name(scheme)
			if s_name in names:
				raise ValueError(f"Duplicate scheme name: {s_name}")
			names.add(s_name)

		return schemes

	def _sync_collection(self) -> None:
		if not self.schemes:
			existing = self.collection.get(include=["metadatas"])["ids"]
			if existing:
				self.collection.delete(ids=existing)
			return

		ids = list(self.schemes_by_id)
		# Skip re-embedding if all scheme IDs are already present in the collection
		if self.collection.count() == len(ids):
			return

		documents = [_scheme_document(scheme) for scheme in self.schemes]
		embeddings = create_embeddings(documents, model=self.embedding_model)
		metadatas = [
			{
				"scheme_name": _scheme_name(scheme),
				"id": scheme.get("id", ""),
				"citizen_eligible": scheme.get("citizen_eligible", True),
			}
			for scheme in self.schemes
		]
		self.collection.upsert(
			ids=ids,
			documents=documents,
			embeddings=embeddings,
			metadatas=metadatas,
		)

	def retrieve_schemes(
		self, profile: dict[str, Any] | str, top_k: int = 15
	) -> list[dict[str, Any]]:
		"""Return the top matching complete scheme records for a profile."""
		if top_k < 1:
			raise ValueError("top_k must be at least 1.")
		if not self.schemes:
			return []

		if isinstance(profile, str):
			query_text = profile
		else:
			query_text = json.dumps(profile, ensure_ascii=False, sort_keys=True)
		query_embedding = create_embeddings(query_text, model=self.embedding_model)[0]
		result = self.collection.query(
			query_embeddings=[query_embedding],
			n_results=min(top_k, len(self.schemes)),
			include=["metadatas"],
		)
		metadata = result["metadatas"][0]
		return [
			self.schemes_by_id[_scheme_id(item["scheme_name"])]
			for item in metadata
			if item and _scheme_id(item["scheme_name"]) in self.schemes_by_id
		]