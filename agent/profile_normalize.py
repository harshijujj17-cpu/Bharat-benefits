"""Normalize citizen profiles from API payloads and older nested test shapes."""

from typing import Any


CANONICAL_FIELDS = (
    "age",
    "gender",
    "state",
    "education",
    "occupation",
    "annual_household_income_inr",
    "category",
    "disability_status",
    "farmer_status",
    "student_status",
    "employment_status",
    "goal",
    "district",
)


def normalize_profile(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return a flat profile dict the agent and search query builder can use."""
    raw = dict(payload or {})
    demographics = raw.get("demographics") if isinstance(raw.get("demographics"), dict) else {}
    financial = (
        raw.get("financial_information")
        if isinstance(raw.get("financial_information"), dict)
        else {}
    )
    education_block = raw.get("education") if isinstance(raw.get("education"), dict) else {}

    education = raw.get("education")
    if isinstance(education, dict):
        education = education.get("level") or education.get("highest_level") or education.get("currently_enrolled")

    # Preserve explicit 0 income: only fall back on None/unset, not falsy values.
    income = raw.get("annual_income")
    if income is None:
        income = raw.get("annual_household_income_inr")
    if income is None:
        income = financial.get("annual_household_income_inr")

    category = raw.get("category") or raw.get("social_category")
    occupation = raw.get("occupation")
    if occupation is None and education:
        text = str(education).lower()
        if any(token in text for token in ("student", "b.tech", "btech", "school", "college")):
            occupation = "student"

    disability = raw.get("disability_status")
    if disability is None and "disability" in raw:
        disability = "Yes" if raw.get("disability") else "No"

    farmer = raw.get("farmer_status")
    if farmer is None and "farmer" in raw:
        farmer = "Yes" if raw.get("farmer") else "No"

    student = raw.get("student_status")
    if student is None and "student" in raw:
        student = "Yes" if raw.get("student") else "No"

    employment = raw.get("employment_status")
    situation = raw.get("current_situation") or raw.get("situation")
    if employment is None and situation:
        text = str(situation).lower()
        if any(token in text for token in ("unemployed", "retired", "self-employed", "employee")):
            employment = situation

    goal = raw.get("goal") or raw.get("goals") or raw.get("support_goal")
    if isinstance(goal, list):
        goal = "; ".join(str(item) for item in goal if item)

    profile = {
        "age": raw.get("age") if raw.get("age") is not None else demographics.get("age"),
        "gender": raw.get("gender") or demographics.get("gender"),
        "state": raw.get("state") or demographics.get("state"),
        "education": education if not isinstance(education, dict) else education_block.get("level"),
        "occupation": occupation,
        "annual_household_income_inr": income,
        "annual_income": income,
        "category": category,
        "disability_status": disability,
        "farmer_status": farmer,
        "student_status": student,
        "employment_status": employment,
        "goal": goal,
        "district": raw.get("district") or demographics.get("district"),
    }
    if isinstance(profile["education"], dict):
        profile["education"] = profile["education"].get("level") or profile["education"].get("highest_level")

    extra = {
        key: value
        for key, value in raw.items()
        if key not in profile and key not in {
            "demographics",
            "financial_information",
            "expected_relevant_schemes",
            "profile_id",
            "description",
            "household_context",
        }
    }
    profile.update(extra)
    return profile
