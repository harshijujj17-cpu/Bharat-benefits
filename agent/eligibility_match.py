"""Lightweight in-memory eligibility scoring used after live retrieval."""

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


def score_scheme(profile: dict[str, Any], scheme: dict[str, Any]) -> float:
    """Return a relevance score (higher = better match) for scheme vs profile."""
    score = 0.0
    eligibility = scheme.get("eligibility") or {}
    eligibility_text = _as_text(eligibility).lower()

    profile_state = _normalise(str(profile.get("state", "")))
    if profile_state and profile_state in _normalise(eligibility_text + " " + _as_text(scheme.get("description"))):
        score += 12
    if profile_state and profile_state in _normalise(_as_text(scheme.get("scheme_name"))):
        score += 6

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

        profile_income = profile.get("annual_household_income_inr") or profile.get("annual_income")
        max_income = eligibility.get("max_income")
        if isinstance(profile_income, (int, float)) and isinstance(max_income, (int, float)):
            if profile_income <= max_income:
                score += 10
            else:
                score -= 12

        profile_cat = _normalise(str(profile.get("category", "")))
        elig_cat = eligibility.get("social_category")
        if elig_cat:
            cats = {_normalise(str(c)) for c in (elig_cat if isinstance(elig_cat, list) else [elig_cat])}
            if profile_cat and profile_cat in cats:
                score += 10

    profile_income = profile.get("annual_household_income_inr") or profile.get("annual_income")
    if isinstance(profile_income, (int, float)) and profile_income >= 800000:
        if any(token in eligibility_text for token in ("bpl", "income limit", "family income", "2.5", "250000", "8 lakh", "lakh")):
            score -= 8

    profile_cat = _normalise(str(profile.get("category", "")))
    blob = _normalise(
        " ".join(
            _as_text(scheme.get(field))
            for field in ("scheme_name", "description", "eligibility", "benefits")
        )
    )
    if profile_cat and profile_cat in blob:
        score += 8

    gender = _normalise(str(profile.get("gender") or ""))
    if gender in {"woman", "women", "female", "girl"}:
        if any(token in blob for token in ("woman", "women", "girl", "female", "kanya")):
            score += 10

    education = _normalise(str(profile.get("education") or ""))
    if education and any(token in blob for token in _tokens(education) | {"student", "scholarship", "btech"}):
        score += 8

    return score


def attach_scores(profile: dict[str, Any], schemes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = []
    for scheme in schemes:
        item = dict(scheme)
        item["_match_score"] = score_scheme(profile, item)
        scored.append(item)
    scored.sort(key=lambda item: -float(item.get("_match_score") or 0))
    return scored
