"""Build live web-search queries from a citizen profile.

Generates multiple complementary queries that strongly encode:
  STATE + NEED + CITIZEN CONTEXT + GOVERNMENT SCHEME/BENEFIT INTENT

The state and need are treated as first-class retrieval constraints —
never diluted into a single generic "India scheme" query.
"""

import json
import logging
from typing import Any

from google.genai import types

from agent import model_config
from agent.profile_normalize import normalize_profile

logger = logging.getLogger(__name__)

# ── Need → search-keyword mapping ────────────────────────────────────────

NEED_KEYWORDS: dict[str, list[str]] = {
    "education": [
        "education scholarship student welfare fee reimbursement post-matric",
        "student scholarship scheme eligibility",
        "education fee reimbursement tuition support",
    ],
    "agriculture": [
        "farmer agriculture scheme subsidy crop assistance",
        "agriculture input assistance irrigation farm support",
        "farmer welfare scheme benefits",
    ],
    "women & children": [
        "women welfare child welfare maternity support protection",
        "women empowerment scheme benefits nutrition",
        "child development women protection scheme",
    ],
    "health": [
        "health insurance medical scheme hospital treatment",
        "health welfare scheme benefits coverage",
    ],
    "housing": [
        "housing scheme affordable house construction subsidy",
        "housing welfare scheme benefits",
    ],
    "employment": [
        "employment scheme job training skill development",
        "employment welfare scheme benefits livelihood",
    ],
    "disability": [
        "disability welfare scheme pension support",
        "disabled persons scheme benefits assistance",
    ],
    "senior citizen": [
        "senior citizen pension scheme old age welfare",
        "elderly welfare scheme benefits",
    ],
    "business": [
        "business loan scheme enterprise startup support",
        "self-employment scheme MSME benefits",
    ],
    "social security": [
        "social security pension scheme welfare benefits",
        "social protection scheme insurance",
    ],
}

# ── Telangana official source focus ───────────────────────────────────────

STATE_DOMAINS: dict[str, str] = {
    "telangana": "telangana.gov.in",
}


def _need_keywords(goal: str) -> list[str]:
    """Return search keyword phrases for the given need/goal."""
    goal_lower = goal.lower().strip()
    for key, keywords in NEED_KEYWORDS.items():
        if key in goal_lower or goal_lower in key:
            return keywords
    # Fallback: use goal text directly
    return [f"{goal} government scheme welfare benefits"]


def _state_domain(state: str) -> str | None:
    """Return the official state government domain, if known."""
    return STATE_DOMAINS.get(state.lower().strip())


def build_template_queries(profile: dict[str, Any]) -> list[str]:
    """Generate deterministic search queries strongly targeting state + need."""
    profile = normalize_profile(profile)
    state = str(profile.get("state") or "Telangana").strip()
    category = str(profile.get("category") or "").strip()
    education = str(profile.get("education") or "").strip()
    gender = str(profile.get("gender") or "").strip()
    occupation = str(profile.get("occupation") or "").strip()
    goal = str(profile.get("goal") or profile.get("other_relevant_information") or "").strip()
    employment = str(profile.get("employment_status") or "").strip()
    farmer = str(profile.get("farmer_status") or "").strip().lower()
    student = str(profile.get("student_status") or "").strip().lower()

    queries: list[str] = []

    # ── Strategy 1: State + Need on myscheme.gov.in (most structured source) ──
    if state and goal:
        queries.append(
            f"site:myscheme.gov.in {state} {goal} scheme eligibility benefits"
        )

    # ── Strategy 2: State + Need + citizen context (unrestricted) ──
    if state and goal:
        citizen_parts = " ".join(
            part for part in (category, education, occupation) if part
        )
        queries.append(
            f"{state} government {goal} scheme official {citizen_parts}".strip()
        )

    # ── Strategy 3: State official portal + need keywords ──
    if state:
        state_domain = _state_domain(state)
        need_kw = _need_keywords(goal) if goal else ["government scheme welfare benefits"]
        if state_domain:
            queries.append(f"site:{state_domain} {need_kw[0]} official")

    # ── Strategy 4: State + Need on gov.in (central + state portals) ──
    if state and goal:
        queries.append(
            f"site:gov.in {state} {goal} scheme official {category}".strip()
        )

    # ── Strategy 5: Unrestricted state + need + official keyword ──
    if state and goal:
        queries.append(
            f"{state} {goal} government benefit scheme official 2024 2025"
        )

    # ── Strategy 6: Need-specific enrichments ──
    if goal:
        for kw_phrase in _need_keywords(goal)[:1]:
            if state:
                queries.append(
                    f"{state} {kw_phrase} official government scheme {category}".strip()
                )

    # ── Strategy 7: Gender-specific ──
    gender_key = gender.lower()
    if gender_key and state and (
        "female" in gender_key or gender_key in {"woman", "women", "girl"}
    ):
        queries.append(
            f"{state} government schemes for women {goal or ''} {category} official".strip()
        )

    # ── Strategy 8: Farmer-specific ──
    if farmer == "yes" and state:
        queries.append(
            f"{state} farmer agriculture scheme benefits official government"
        )

    # ── Strategy 9: Student-specific ──
    if student == "yes" and state:
        queries.append(
            f"{state} student scholarship scheme eligibility {category} official government"
        )

    # ── Strategy 10: Employment-specific ──
    if employment and state:
        queries.append(
            f"{state} {employment} government scheme benefits welfare official"
        )

    # Deduplicate while preserving order
    cleaned: list[str] = []
    seen: set[str] = set()
    for query in queries:
        compact = " ".join(query.split())
        key = compact.lower()
        if compact and key not in seen:
            seen.add(key)
            cleaned.append(compact)
    return cleaned[:10]


def _gemini_queries(profile: dict[str, Any], client: Any | None = None) -> list[str]:
    """Optional LLM-written queries.

    Query generation is enrichment only — the deterministic template queries
    always run — so a failure here degrades to ``[]`` but is logged rather than
    silently swallowed.
    """
    state = str(profile.get("state") or "Telangana").strip()
    goal = str(profile.get("goal") or "").strip()
    state_instruction = ""
    if state:
        state_instruction = (
            f"IMPORTANT: All queries MUST include the state name '{state}' prominently. "
            f"Focus on schemes specifically from {state} state government or Central Government "
            f"schemes applicable in {state}. "
        )
    need_instruction = ""
    if goal:
        need_instruction = (
            f"Focus queries on '{goal}'-related schemes. "
        )

    prompt = (
        "Generate 3 diverse web search queries to find CURRENT official Indian government "
        "schemes for this citizen profile. "
        f"{state_instruction}"
        f"{need_instruction}"
        "Prioritize Telangana government and department portals, myscheme.gov.in, "
        "and relevant official gov.in or nic.in sources. Include Telangana and "
        "the need/goal domain in every query. Return JSON "
        "{\"queries\": [\"...\", \"...\", \"...\"]}. "
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
        return [str(item).strip() for item in queries if str(item).strip()][:10]
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
    return queries[:10]
