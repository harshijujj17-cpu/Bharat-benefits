"""Ground Gemini explanations in schemes retrieved from live search."""

import json
import logging
from typing import Any

from google.genai import types

from agent import model_config
from agent.prompts import (
	ELIGIBILITY_NOTICE,
	RECOMMENDATION_RESPONSE_SCHEMA,
	SYSTEM_INSTRUCTION,
	build_recommendation_prompt,
)

logger = logging.getLogger(__name__)

FACT_FIELDS = (
	"description",
	"eligibility",
	"benefits",
	"required_documents",
	"application_process",
	"application_url",
	"official_source_url",
	"government_department",
	"important_dates",
)
FIELD_LABELS = {
	"description": "Description",
	"eligibility": "Eligibility information",
	"benefits": "Benefits",
	"required_documents": "Required documents",
	"application_process": "Application process",
	"application_url": "Application URL",
	"official_source_url": "Official source URL",
	"official_source": "Official source URL",
	"government_department": "Government / department",
	"important_dates": "Important dates",
	"helpline": "Helpline",
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
	"description": ("description",),
	"eligibility": ("eligibility",),
	"benefits": ("benefits",),
	"required_documents": ("required_documents", "documents"),
	"application_process": ("application_process",),
	"application_url": ("application_url", "apply_url"),
	"official_source_url": ("official_source_url", "official_source", "apply_url"),
	"government_department": ("government_department", "department", "government"),
	"important_dates": ("important_dates",),
}


def _resolve_field(scheme: dict[str, Any], canonical: str) -> Any:
	"""Return the first non-empty value for *canonical* using FIELD_ALIASES."""
	for key in FIELD_ALIASES.get(canonical, (canonical,)):
		value = scheme.get(key)
		if value is not None and value != "" and value != []:
			return value
	return None


def _format_eligibility(value: Any) -> Any:
	"""Format the eligibility struct into a human-readable list if it is a dict."""
	if not isinstance(value, dict):
		return value
	lines: list[str] = []
	label_map = {
		"min_age": "Minimum age",
		"max_age": "Maximum age",
		"max_income": "Maximum annual income (INR)",
		"state": "State/UT",
		"area": "Area",
		"gender": "Gender",
		"occupation": "Occupation",
		"social_category": "Social category",
	}
	for key, label in label_map.items():
		val = value.get(key)
		if val is None:
			continue
		if isinstance(val, list):
			lines.append(f"{label}: {', '.join(str(v) for v in val)}")
		else:
			lines.append(f"{label}: {val}")
	return lines if lines else None


def _parse_model_response(response_text: str) -> dict[str, dict[str, Any]]:
	try:
		payload = json.loads(response_text)
	except json.JSONDecodeError as exc:
		raise ValueError("Gemini returned invalid JSON for the recommendations.") from exc

	recommendations = payload.get("recommendations") if isinstance(payload, dict) else None
	if not isinstance(recommendations, list):
		raise ValueError("Gemini response must contain a recommendations list.")

	parsed: dict[str, dict[str, Any]] = {}
	for item in recommendations:
		if not isinstance(item, dict):
			raise ValueError("Each Gemini recommendation must be a JSON object.")
		scheme_name = item.get("scheme_name")
		explanation = item.get("relevance_explanation")
		missing_information = item.get("missing_information")
		if not isinstance(scheme_name, str) or not isinstance(explanation, str):
			raise ValueError("Gemini recommendation is missing its name or explanation.")
		if not isinstance(missing_information, list) or not all(
			isinstance(value, str) for value in missing_information
		):
			raise ValueError("Gemini missing_information must be a list of strings.")
		generated_text = [explanation, *missing_information]
		if any("you are definitely eligible" in value.casefold() for value in generated_text):
			raise ValueError("Gemini returned prohibited definitive-eligibility wording.")
		if scheme_name in parsed:
			raise ValueError(f"Gemini returned a duplicate scheme: {scheme_name}")
		status = item.get("eligibility_status") or "cannot_confirm"
		if status not in {"relevant", "not_relevant", "cannot_confirm", "likely_not_eligible"}:
			status = "cannot_confirm"
		parsed[scheme_name] = {
			"relevance_explanation": explanation,
			"missing_information": missing_information,
			"eligibility_status": status,
		}
	return parsed


def _build_recommendation(
	scheme: dict[str, Any], explanation: dict[str, Any]
) -> dict[str, Any]:
	result = {
		"scheme_name": scheme["scheme_name"],
		"relevance_explanation": explanation["relevance_explanation"],
		"eligibility_notice": ELIGIBILITY_NOTICE,
		"missing_information": list(explanation["missing_information"]),
		"citizen_eligible": scheme.get("citizen_eligible", True),
		"eligibility_status": explanation.get("eligibility_status", "cannot_confirm"),
	}

	for field in FACT_FIELDS:
		value = _resolve_field(scheme, field)
		if field == "eligibility" and isinstance(value, dict):
			value = _format_eligibility(value)
		if value is None or value == "" or value == []:
			result["missing_information"].append(
				f"The retrieved scheme data does not include {FIELD_LABELS[field].lower()}."
			)
		else:
			result[field] = value

	helpline = scheme.get("helpline")
	if helpline is not None and helpline != "" and helpline != []:
		result["helpline"] = helpline

	if scheme.get("source_verification"):
		result["source_verification"] = scheme["source_verification"]

	if not result.get("official_source_url"):
		result["missing_information"].append(
			"The retrieved scheme data does not include an official source URL."
		)
	else:
		result["official_source"] = result["official_source_url"]

	result["missing_information"] = list(dict.fromkeys(result["missing_information"]))
	return result


def recommend_schemes(
	profile: dict[str, Any],
	retrieved_schemes: list[dict[str, Any]],
	client: Any | None = None,
	model_name: str | None = None,
) -> dict[str, Any]:
	"""Explain live-retrieved schemes and attach their source data.

	Pass the result of live retrieval as ``retrieved_schemes``.
	No local scheme dataset is loaded or searched here.
	"""
	if not retrieved_schemes:
		return {"recommendations": [], "notice": "No schemes were retrieved for this profile."}

	schemes_by_name: dict[str, dict[str, Any]] = {}
	for scheme in retrieved_schemes:
		scheme_name = scheme.get("scheme_name") or scheme.get("name") or scheme.get("id")
		if not isinstance(scheme_name, str) or not scheme_name:
			raise ValueError("Every retrieved scheme must have a scheme_name.")
		scheme["scheme_name"] = scheme_name
		if scheme_name in schemes_by_name:
			continue
		schemes_by_name[scheme_name] = scheme

	if client is not None:
		response = model_config.generate_with_fallback(
			client,
			build_recommendation_prompt(profile, retrieved_schemes),
			config=types.GenerateContentConfig(
				system_instruction=SYSTEM_INSTRUCTION,
				response_mime_type="application/json",
				response_schema=RECOMMENDATION_RESPONSE_SCHEMA,
				temperature=0.2,
			),
			model_name=model_name,
			purpose="eligibility",
		)
	else:
		from agent import llm_client

		response = llm_client.generate(
			build_recommendation_prompt(profile, retrieved_schemes),
			system_instruction=SYSTEM_INSTRUCTION,
			response_schema=RECOMMENDATION_RESPONSE_SCHEMA,
			temperature=0.2,
			model_name=model_name,
			purpose="eligibility",
		)

	explanations = _parse_model_response(response.text)
	unexpected_names = explanations.keys() - schemes_by_name.keys()
	missing_names = schemes_by_name.keys() - explanations.keys()
	if unexpected_names or missing_names:
		raise ValueError(
			"Gemini response did not match the retrieved schemes. "
			f"Unexpected: {sorted(unexpected_names)}; missing: {sorted(missing_names)}"
		)

	return {
		"recommendations": [
			_build_recommendation(scheme, explanations[scheme_name])
			for scheme_name, scheme in schemes_by_name.items()
		]
	}
