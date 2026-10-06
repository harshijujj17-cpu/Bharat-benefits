"""Extract a structured citizen profile from free-form text or speech transcripts.

Uses Gemini with a strict JSON response schema so every field is present.
Unknown values are returned as ``null`` — the model is instructed never to
invent information.
"""

import json
import logging
from typing import Any

from google.genai import types

from agent import model_config

logger = logging.getLogger(__name__)

# ── Response schema ──────────────────────────────────────────────────────

PROFILE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "age":                {"type": "INTEGER", "nullable": True},
        "gender":             {"type": "STRING",  "nullable": True},
        "state":              {"type": "STRING",  "nullable": True},
        "education":          {"type": "STRING",  "nullable": True},
        "occupation":         {"type": "STRING",  "nullable": True},
        "annual_household_income_inr": {"type": "INTEGER", "nullable": True},
        "category":           {"type": "STRING",  "nullable": True},
        "disability_status":  {"type": "STRING",  "nullable": True},
        "farmer_status":      {"type": "STRING",  "nullable": True},
    },
    "required": [
        "age", "gender", "state", "education", "occupation",
        "annual_household_income_inr", "category",
        "disability_status", "farmer_status",
    ],
}

# ── System prompt ────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM_INSTRUCTION = """\
You are a structured-data extraction assistant.  You receive free-form text
(possibly a speech transcript) describing a citizen's personal situation.

Your ONLY task is to extract the following fields and return them as JSON:

  age                         – integer or null
  gender                      – string or null  (e.g. "Woman", "Man")
  state                       – Indian state/UT name or null
  education                   – highest level or null
  occupation                  – string or null
  annual_household_income_inr – integer (annual, INR) or null
  category                    – social category (General/SC/ST/OBC/EWS) or null
  disability_status           – "Yes", "No", or null
  farmer_status               – "Yes", "No", or null

Rules:
- Return ONLY the JSON object.  No commentary, no markdown fences.
- If a value is not stated or cannot be reliably inferred, set it to null.
- Never invent, assume, or hallucinate information.
- For income: if a monthly figure is mentioned, multiply by 12.
- Normalise state names to their standard English form (e.g. "UP" → "Uttar Pradesh").
- Normalise education to one of: "No formal schooling", "Primary",
  "Middle school", "Secondary", "Higher secondary", "Diploma",
  "Bachelor's degree", "Postgraduate", or keep the original if none match.
""".strip()


# ── Public API ───────────────────────────────────────────────────────────

def extract_profile(
    text: str,
    *,
    client: Any | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Parse *text* into a structured citizen profile dict.

    Parameters
    ----------
    text : str
        Free-form description of the citizen (may come from speech).
    client : optional
        Pre-built ``genai.Client``.
    model_name : optional
        Override for the Gemini model.

    Returns
    -------
    dict
        Profile with the nine canonical fields.  Missing values are ``None``.
    """
    if not text or not text.strip():
        return _empty_profile()

    if client is not None:
        response = model_config.generate_with_fallback(
            client,
            text.strip(),
            config=types.GenerateContentConfig(
                system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=PROFILE_RESPONSE_SCHEMA,
                temperature=0.0,
            ),
            model_name=model_name,
            purpose="profile-extraction",
        )
    else:
        from agent import llm_client

        response = llm_client.generate(
            text.strip(),
            system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
            response_schema=PROFILE_RESPONSE_SCHEMA,
            temperature=0.0,
            model_name=model_name,
            purpose="profile-extraction",
        )

    return _parse_response(response.text)


# ── Internals ────────────────────────────────────────────────────────────

_FIELDS = (
    "age", "gender", "state", "education", "occupation",
    "annual_household_income_inr", "category",
    "disability_status", "farmer_status",
)


def _empty_profile() -> dict[str, Any]:
    return {field: None for field in _FIELDS}


def _parse_response(text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini returned invalid JSON for profile extraction.") from exc

    if not isinstance(raw, dict):
        raise ValueError("Gemini profile response must be a JSON object.")

    profile: dict[str, Any] = {}
    for field in _FIELDS:
        value = raw.get(field)
        # Normalise empty strings to None
        if isinstance(value, str) and not value.strip():
            value = None
        profile[field] = value

    return profile
