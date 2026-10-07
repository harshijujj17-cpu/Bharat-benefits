"""Lightweight in-memory eligibility scoring used after live retrieval.

State mismatch and need mismatch receive heavy penalties so that a
Karnataka agriculture scheme never outranks a Telangana education scheme
for a Telangana + Education request.
"""

import json
import re
from typing import Any


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    return set(_normalise(text).split())


# ── Indian state names for mismatch detection ─────────────────────────────

_INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya",
    "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim",
    "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
    "west bengal", "delhi", "jammu and kashmir", "ladakh", "chandigarh",
    "puducherry",
}


def _detect_states_in_text(text: str) -> set[str]:
    """Detect Indian state names in text."""
    text_lower = text.lower()
    return {state for state in _INDIAN_STATES if state in text_lower}


def score_scheme(profile: dict[str, Any], scheme: dict[str, Any]) -> float:
    """Return a relevance score (higher = better match) for scheme vs profile."""
    score = 0.0
    eligibility = scheme.get("eligibility") or {}
    eligibility_text = _as_text(eligibility).lower()

    # Build full scheme text blob for keyword searches
    blob = _normalise(
        " ".join(
            _as_text(scheme.get(field))
            for field in ("scheme_name", "description", "eligibility", "benefits",
                          "official_source_url", "government_department")
        )
    )

    # ── State match / mismatch (major factor) ──────────────────────────
    profile_state = _normalise(str(profile.get("state", "")))
    if profile_state:
        scheme_text = _as_text(scheme.get("scheme_name")) + " " + eligibility_text + " " + _as_text(scheme.get("description"))
        mentioned_states = _detect_states_in_text(scheme_text)

        if profile_state in blob:
            score += 15  # Strong state match
        if profile_state in _normalise(_as_text(scheme.get("scheme_name"))):
            score += 8  # State in scheme name (very strong signal)

        # Central/national scheme bonus
        central_indicators = {"central government", "government of india", "pradhan mantri",
                              "ministry of", "national", "all india", "pan india"}
        is_central = any(ind in blob for ind in central_indicators)
        if is_central and profile_state not in mentioned_states:
            score += 5  # Central scheme, still applicable

        # PENALTY: Another state mentioned exclusively (not our state, not central)
        other_states = mentioned_states - {profile_state}
        if other_states and profile_state not in mentioned_states and not is_central:
            score -= 30  # Major penalty for wrong-state scheme

    # ── Age match ────────────────────────────────────────────────────────
    profile_age = profile.get("age")
    if isinstance(eligibility, dict):
        if isinstance(profile_age, (int, float)) and profile_age > 0:
            min_age = eligibility.get("min_age")
            max_age = eligibility.get("max_age")
            if min_age is not None and profile_age < min_age:
                score -= 15
            elif max_age is not None and profile_age > max_age:
                score -= 15
            else:
                score += 5

        # ── Income match ──
        profile_income = profile.get("annual_household_income_inr") or profile.get("annual_income")
        max_income = eligibility.get("max_income")
        if isinstance(profile_income, (int, float)) and isinstance(max_income, (int, float)):
            if profile_income <= max_income:
                score += 10
            else:
                score -= 12

        # ── Category match ──
        profile_cat = _normalise(str(profile.get("category", "")))
        elig_cat = eligibility.get("social_category")
        if elig_cat:
            cats = {_normalise(str(c)) for c in (elig_cat if isinstance(elig_cat, list) else [elig_cat])}
            if profile_cat and profile_cat in cats:
                score += 10

    # ── Income-limit BPL check ──
    profile_income = profile.get("annual_household_income_inr") or profile.get("annual_income")
    if isinstance(profile_income, (int, float)) and profile_income >= 800000:
        if any(token in eligibility_text for token in ("bpl", "income limit", "family income", "2.5", "250000", "8 lakh", "lakh")):
            score -= 8

    # ── Category keyword match in full scheme text ──
    profile_cat = _normalise(str(profile.get("category", "")))
    if profile_cat and profile_cat in blob:
        score += 8

    # ── Gender match ──
    gender = _normalise(str(profile.get("gender") or ""))
    if gender in {"woman", "women", "female", "girl"}:
        if any(token in blob for token in ("woman", "women", "girl", "female", "kanya")):
            score += 10

    # ── Education match ──
    education = _normalise(str(profile.get("education") or ""))
    if education and any(token in blob for token in _tokens(education) | {"student", "scholarship", "btech"}):
        score += 8

    # ── Need/goal match ──
    goal = _normalise(str(profile.get("goal") or ""))
    if goal and any(token in blob for token in _tokens(goal)):
        score += 10

    # ── Official source bonus ──
    source = str(scheme.get("official_source_url") or "").lower()
    if ".gov.in" in source or ".nic.in" in source:
        score += 5

    return score


def attach_scores(profile: dict[str, Any], schemes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = []
    for scheme in schemes:
        item = dict(scheme)
        item["_match_score"] = score_scheme(profile, item)
        scored.append(item)
    scored.sort(key=lambda item: -float(item.get("_match_score") or 0))
    return scored
