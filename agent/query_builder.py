"""Build live web-search queries from a citizen profile."""

import json
import logging
from typing import Any

from google.genai import types

from agent import model_config
from agent.profile_normalize import normalize_profile

logger = logging.getLogger(__name__)


def build_template_queries(profile: dict[str, Any]) -> list[str]:
    profile = normalize_profile(profile)
    state = str(profile.get("state") or "").strip()
    category = str(profile.get("category") or "").strip()
    education = str(profile.get("education") or "").strip()
    gender = str(profile.get("gender") or "").strip()
    occupation = str(profile.get("occupation") or "").strip()
    goal = str(profile.get("goal") or profile.get("other_relevant_information") or "").strip()
    employment = str(profile.get("employment_status") or "").strip()
    farmer = str(profile.get("farmer_status") or "").strip().lower()
    student = str(profile.get("student_status") or "").strip().lower()
    age = profile.get("age")

    subject = " ".join(
        part for part in (state, category, education, occupation, "government scheme") if part
    ).strip()
    queries = [
        f"site:myscheme.gov.in {subject} eligibility benefits".strip(),
        f"site:gov.in {state} {category} {education} scholarship OR scheme official".strip(),
    ]
    if state:
        queries.append(
            f"site:{state.lower().replace(' ', '')}.gov.in {education} {category} student scheme".strip()
        )
    gender_key = gender.lower()
    if gender_key and (
        "female" in gender_key or gender_key in {"woman", "women", "girl"}
    ):
        queries.append(
            f"site:gov.in {state} schemes for women students {education} {category}".strip()
        )
    if occupation:
        queries.append(f"site:gov.in India {occupation} {state} government scheme official".strip())
    if employment:
        queries.append(f"site:myscheme.gov.in {state} {employment} benefits scheme eligibility".strip())
    if goal:
        queries.append(f"site:gov.in {state} {goal} government benefit scheme official".strip())
    if farmer == "yes":
        queries.append(f"site:gov.in {state} farmer agriculture scheme benefits official".strip())
    if student == "yes":
        queries.append(f"site:gov.in {state} student scholarship scheme eligibility official".strip())
    if age:
        queries.append(
            f"myscheme.gov.in schemes for {age} year old {education or occupation} {state} {category}".strip()
        )

    cleaned: list[str] = []
    seen: set[str] = set()
    for query in queries:
        compact = " ".join(query.split())
        key = compact.lower()
        if compact and key not in seen:
            seen.add(key)
            cleaned.append(compact)
    return cleaned[:5]


def _gemini_queries(profile: dict[str, Any], client: Any | None = None) -> list[str]:
    """Optional LLM-written queries.

    Query generation is enrichment only — the deterministic template queries
    always run — so a failure here degrades to ``[]`` but is logged rather than
    silently swallowed.
    """
    prompt = (
        "Generate 2 web search queries to find CURRENT official Indian government "
        "schemes for this citizen profile. Prefer site:gov.in, myscheme.gov.in, "
        "and official state portals. Return JSON {\"queries\": [\"...\", \"...\"]}. "
        "Do not invent scheme names.\n"
        f"{json.dumps(normalize_profile(profile), ensure_ascii=False)}"
    )
    try:
        if client is not None:
            gemini_client = client
            response = model_config.generate_with_fallback(
                gemini_client,
                prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
                purpose="query-generation",
            )
        else:
            from agent import llm_client

            response = llm_client.generate(
                prompt,
                temperature=0.1,
                purpose="query-generation",
            )
        payload = json.loads(response.text)
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort
        logger.warning(
            "LLM query generation unavailable (%s: %s)", type(exc).__name__, exc
        )
        return []

    queries = payload.get("queries") if isinstance(payload, dict) else None
    if isinstance(queries, list):
        return [str(item).strip() for item in queries if str(item).strip()][:2]
    return []


def build_search_queries(
    profile: dict[str, Any],
    *,
    client: Any | None = None,
    include_llm: bool = True,
) -> list[str]:
    queries = build_template_queries(profile)
    if include_llm:
        for extra in _gemini_queries(profile, client=client):
            if extra.lower() not in {item.lower() for item in queries}:
                queries.append(extra)
    return queries[:6]
