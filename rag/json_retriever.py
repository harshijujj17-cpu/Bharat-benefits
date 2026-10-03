"""Pure-JSON retriever that replaces ChromaDB with keyword + field matching.

Loads schemes from ``data/schemes.json`` and scores each scheme against the
citizen profile using a lightweight multi-signal heuristic (category overlap,
state match, income/age range checks, occupation keywords).  No embeddings
or vector database required.

Public API mirrors ``SchemeRetriever`` so it can be used as a drop-in swap.
"""

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMES_PATH = PROJECT_ROOT / "data" / "schemes.json"


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _scheme_name(scheme: dict[str, Any]) -> str:
    return (
        scheme.get("scheme_name")
        or scheme.get("name")
        or scheme.get("id")
        or "Unknown Scheme"
    )


def _normalise(text: str) -> str:
    """Lowercase and strip non-alphanumeric chars for matching."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def _tokens(text: str) -> set[str]:
    return set(_normalise(text).split())


# ── Scoring helpers ──────────────────────────────────────────────────────

def _score_scheme(profile: dict[str, Any], scheme: dict[str, Any]) -> float:
    """Return a relevance score (higher = better match) for scheme vs profile."""
    score = 0.0

    eligibility = scheme.get("eligibility") or {}
    if isinstance(eligibility, str):
        eligibility = {}

    # 1. State match
    profile_state = _normalise(str(profile.get("state", "")))
    elig_state = eligibility.get("state")
    if elig_state:
        if isinstance(elig_state, list):
            elig_states = {_normalise(s) for s in elig_state}
        else:
            elig_states = {_normalise(str(elig_state))}
        if profile_state and profile_state in elig_states:
            score += 20
        elif elig_state is None or elig_states == {""}:
            score += 5  # open to all states
    else:
        score += 5  # no state restriction

    # 2. Age range
    profile_age = profile.get("age")
    if isinstance(profile_age, (int, float)) and profile_age > 0:
        min_age = eligibility.get("min_age")
        max_age = eligibility.get("max_age")
        if min_age is not None and profile_age < min_age:
            score -= 15
        elif max_age is not None and profile_age > max_age:
            score -= 15
        else:
            score += 5

    # 3. Income ceiling
    profile_income = profile.get("annual_household_income_inr")
    max_income = eligibility.get("max_income")
    if isinstance(profile_income, (int, float)) and isinstance(max_income, (int, float)):
        if profile_income <= max_income:
            score += 10
        else:
            score -= 10

    # 4. Gender
    profile_gender = _normalise(str(profile.get("gender", "")))
    elig_gender = eligibility.get("gender")
    if elig_gender:
        if isinstance(elig_gender, list):
            elig_genders = {_normalise(g) for g in elig_gender}
        else:
            elig_genders = {_normalise(str(elig_gender))}
        if profile_gender and profile_gender in elig_genders:
            score += 10
        elif profile_gender and profile_gender not in elig_genders and elig_genders != {""}:
            score -= 5

    # 5. Occupation / farmer match
    profile_occ = _normalise(str(profile.get("occupation", "")))
    profile_farmer = _normalise(str(profile.get("farmer_status", "")))
    elig_occ = eligibility.get("occupation")
    if elig_occ:
        if isinstance(elig_occ, list):
            elig_occs = {_normalise(o) for o in elig_occ}
        else:
            elig_occs = {_normalise(str(elig_occ))}
        # Check if any occupation keyword matches profile occupation or farmer status
        occ_tokens = _tokens(profile_occ)
        if any(o in profile_occ or o in occ_tokens for o in elig_occs):
            score += 15
        elif "farmer" in elig_occs and profile_farmer == "yes":
            score += 15
        else:
            score -= 5

    # 6. Social category
    profile_cat = _normalise(str(profile.get("category", "")))
    elig_cat = eligibility.get("social_category")
    if elig_cat:
        if isinstance(elig_cat, list):
            elig_cats = {_normalise(c) for c in elig_cat}
        else:
            elig_cats = {_normalise(str(elig_cat))}
        if profile_cat and profile_cat in elig_cats:
            score += 10

    # 7. Category / keyword overlap with scheme description
    desc = _normalise(scheme.get("description", "") or "")
    category = _normalise(scheme.get("category", "") or "")
    profile_tokens = set()
    for field in ("occupation", "state", "education", "category", "other_relevant_information"):
        val = profile.get(field)
        if val:
            profile_tokens |= _tokens(str(val))

    overlap = profile_tokens & (_tokens(desc) | _tokens(category))
    score += len(overlap) * 2

    # 8. Disability match
    profile_dis = _normalise(str(profile.get("disability_status", "")))
    if profile_dis == "yes":
        if "disab" in desc or "divyang" in desc or "handicap" in desc:
            score += 15

    return score


class JSONSchemeRetriever:
    """Score-based retriever that reads directly from schemes.json."""

    def __init__(
        self,
        schemes_path: str | Path = DEFAULT_SCHEMES_PATH,
        **kwargs: Any,
    ) -> None:
        self.schemes_path = Path(schemes_path)
        self.schemes = self._load_schemes()

    def _load_schemes(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.schemes_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Scheme data not found: {self.schemes_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {self.schemes_path}") from exc

        if not isinstance(data, list):
            raise ValueError("Scheme data must be a JSON array.")
        return data

    def retrieve_schemes(
        self, profile: dict[str, Any] | str, top_k: int = 15
    ) -> list[dict[str, Any]]:
        """Return the top matching scheme records for a profile."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        if not self.schemes:
            return []

        if isinstance(profile, str):
            # Minimal handling for string queries
            profile_dict: dict[str, Any] = {"other_relevant_information": profile}
        else:
            profile_dict = profile

        scored = [
            (_score_scheme(profile_dict, scheme), idx, scheme)
            for idx, scheme in enumerate(self.schemes)
        ]
        scored.sort(key=lambda x: (-x[0], x[1]))

        return [scheme for _score, _idx, scheme in scored[:top_k]]
