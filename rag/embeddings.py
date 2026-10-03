"""Embedding helpers supporting sentence-transformers and Gemini embeddings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_NAME = "gemini-embedding-001"


@lru_cache(maxsize=1)
def load_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> Any:
	"""Load and cache the configured embedding model or client."""
	if model_name == "gemini-embedding-001":
		from google import genai
		from agent.secrets import get_api_key
		return ("gemini", genai.Client(api_key=get_api_key()))

	try:
		from sentence_transformers import SentenceTransformer
	except ImportError as exc:
		raise RuntimeError(
			"Sentence Transformers is not installed. Run: pip install -r requirements.txt"
		) from exc

	return ("sentence-transformer", SentenceTransformer(model_name))


def create_embeddings(
	texts: str | Sequence[str], model: Any | None = None, model_name: str = DEFAULT_MODEL_NAME
) -> list[list[float]]:
	"""Create normalized embeddings for one string or a sequence of strings."""
	if isinstance(texts, str):
		input_texts = [texts]
	else:
		input_texts = list(texts)

	if not input_texts:
		return []

	embedding_model = model or load_embedding_model(model_name)

	if isinstance(embedding_model, tuple) and embedding_model[0] == "gemini":
		client = embedding_model[1]
		results: list[list[float]] = []
		batch_size = 10
		for i in range(0, len(input_texts), batch_size):
			chunk = input_texts[i : i + batch_size]
			for attempt in range(5):
				try:
					response = client.models.embed_content(
						model="gemini-embedding-001",
						contents=chunk,
					)
					if hasattr(response, "embeddings") and response.embeddings:
						for emb in response.embeddings:
							results.append(emb.values)
					elif hasattr(response, "embedding") and response.embedding:
						results.append(response.embedding.values)
					break
				except Exception as exc:
					if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
						import time
						time.sleep(5 * (attempt + 1))
					else:
						raise exc
			import time
			time.sleep(0.5)
		return results

	# Fallback or sentence-transformers
	st_model = embedding_model[1] if isinstance(embedding_model, tuple) else embedding_model
	vectors = st_model.encode(
		input_texts,
		convert_to_numpy=True,
		normalize_embeddings=True,
		show_progress_bar=False,
	)
	return vectors.tolist()