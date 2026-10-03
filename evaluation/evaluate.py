"""Evaluate recommendations against the project's labeled test profiles."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from agent.recommendation import recommend_schemes
from rag.retriever import SchemeRetriever


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "data" / "test_profiles.json"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "evaluation" / "evaluation_results.json"


def _load_profiles(path: Path) -> list[dict[str, Any]]:
	try:
		profiles = json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError as exc:
		raise FileNotFoundError(f"Test profiles file not found: {path}") from exc
	except json.JSONDecodeError as exc:
		raise ValueError(f"Test profiles file is not valid JSON: {path}") from exc

	if not isinstance(profiles, list):
		raise ValueError("Test profiles must be a JSON array.")
	for index, profile in enumerate(profiles):
		if not isinstance(profile, dict):
			raise ValueError(f"Test profile at index {index} must be a JSON object.")
		if not isinstance(profile.get("expected_relevant_schemes"), list):
			raise ValueError(
				f"Test profile at index {index} needs expected_relevant_schemes as a list."
			)
	return profiles


def _scheme_names(values: Any) -> set[str]:
	if not isinstance(values, list):
		return set()
	return {
		value.strip()
		for value in values
		if isinstance(value, str) and value.strip()
	}


def _recommendation_profile(profile: dict[str, Any]) -> dict[str, Any]:
	"""Remove evaluation labels and IDs before retrieval or recommendation."""
	return {
		key: value
		for key, value in profile.items()
		if key not in {"profile_id", "expected_relevant_schemes"}
	}


def _score(expected: set[str], predicted: set[str]) -> dict[str, float]:
	correct = len(expected & predicted)
	precision = correct / len(predicted) if predicted else float(not expected)
	recall = correct / len(expected) if expected else float(not predicted)
	f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
	return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_profiles(
	profiles: list[dict[str, Any]],
	retriever: Any,
	recommender: Callable[..., dict[str, Any]] = recommend_schemes,
	top_k: int = 3,
) -> dict[str, Any]:
	"""Run the real retrieval and recommendation path for each test profile."""
	results = []
	total_correct = 0
	total_expected = 0
	total_predicted = 0
	exact_matches = 0
	successful = 0

	for index, profile in enumerate(profiles):
		profile_id = str(profile.get("profile_id", f"profile-{index + 1}"))
		expected = _scheme_names(profile.get("expected_relevant_schemes"))
		recommendation_profile = _recommendation_profile(profile)
		try:
			retrieved = retriever.retrieve_schemes(recommendation_profile, top_k=top_k)
			recommendation_result = recommender(recommendation_profile, retrieved)
			recommendations = recommendation_result.get("recommendations", [])
			predicted = _scheme_names(
				[
					item.get("scheme_name")
					for item in recommendations
					if isinstance(item, dict)
				]
			)
			correct = expected & predicted
			scores = _score(expected, predicted)
			successful += 1
			total_correct += len(correct)
			total_expected += len(expected)
			total_predicted += len(predicted)
			exact_matches += expected == predicted
			results.append(
				{
					"profile_id": profile_id,
					"status": "ok",
					"expected_schemes": sorted(expected),
					"retrieved_schemes": sorted(
						_scheme_names(
							[
								item.get("scheme_name")
								for item in retrieved
								if isinstance(item, dict)
							]
						)
					),
					"recommended_schemes": sorted(predicted),
					"correct_schemes": sorted(correct),
					**scores,
				}
			)
		except Exception as exc:
			results.append(
				{
					"profile_id": profile_id,
					"status": "error",
					"error_type": type(exc).__name__,
				}
			)

	micro_precision = (
		total_correct / total_predicted if total_predicted else float(total_expected == 0)
	)
	micro_recall = (
		total_correct / total_expected if total_expected else float(total_predicted == 0)
	)
	micro_f1 = (
		2 * micro_precision * micro_recall / (micro_precision + micro_recall)
		if micro_precision + micro_recall
		else 0.0
	)

	return {
		"run_at_utc": datetime.now(timezone.utc).isoformat(),
		"profiles_total": len(profiles),
		"profiles_succeeded": successful,
		"profiles_failed": len(profiles) - successful,
		"top_k": top_k,
		"micro_precision": micro_precision,
		"micro_recall": micro_recall,
		"micro_f1": micro_f1,
		"exact_match_rate": exact_matches / successful if successful else 0.0,
		"results": results,
	}


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		description="Evaluate ChromaDB and Gemini recommendations against labeled profiles."
	)
	parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES_PATH)
	parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH)
	parser.add_argument("--top-k", type=int, default=3)
	parser.add_argument("--limit", type=int, help="Evaluate only the first N profiles.")
	args = parser.parse_args(argv)

	if args.top_k < 1:
		parser.error("--top-k must be at least 1")
	if args.limit is not None and args.limit < 1:
		parser.error("--limit must be at least 1")

	load_dotenv(PROJECT_ROOT / ".env")
	if not os.getenv("GEMINI_API_KEY"):
		print(
			"GEMINI_API_KEY is not set. Add it to Government-Scheme-Agent/.env.",
			file=sys.stderr,
		)
		return 2

	try:
		profiles = _load_profiles(args.profiles)
		if args.limit is not None:
			profiles = profiles[: args.limit]
		retriever = SchemeRetriever()
		report = evaluate_profiles(profiles, retriever, top_k=args.top_k)
		args.output.parent.mkdir(parents=True, exist_ok=True)
		args.output.write_text(
			json.dumps(report, ensure_ascii=False, indent=2) + "\n",
			encoding="utf-8",
		)
	except Exception as exc:
		print(f"Evaluation could not start ({type(exc).__name__}).", file=sys.stderr)
		return 1

	print(
		f"Evaluated {report['profiles_succeeded']}/{report['profiles_total']} profiles; "
		f"failed: {report['profiles_failed']}"
	)
	print(
		"Micro precision: {micro_precision:.3f}; recall: {micro_recall:.3f}; "
		"F1: {micro_f1:.3f}; exact match: {exact_match_rate:.3f}".format(**report)
	)
	print(f"Results saved to {args.output.resolve()}")
	return 0 if report["profiles_failed"] == 0 else 1


if __name__ == "__main__":
	raise SystemExit(main())