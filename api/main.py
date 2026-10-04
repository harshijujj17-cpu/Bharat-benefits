"""FastAPI service for live government-scheme recommendations."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from agent.pipeline import recommend_for_profile, search_schemes
from agent.profile_normalize import normalize_profile
from rag.live_retriever import LiveSearchError

app = FastAPI(
    title="Government Scheme Recommendation API",
    description=(
        "Recommends current Indian government schemes using live web retrieval "
        "from official sources. Scheme records are not stored locally."
    ),
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CitizenProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    age: int | None = None
    education: str | None = None
    state: str | None = None
    category: str | None = None
    annual_income: int | None = None
    annual_household_income_inr: int | None = None
    gender: str | None = None
    occupation: str | None = None
    disability_status: str | None = None
    farmer_status: str | None = None
    student_status: str | None = None
    employment_status: str | None = None
    goal: str | None = None
    district: str | None = None
    current_situation: str | None = None
    other_relevant_information: str | None = None


class RecommendRequest(CitizenProfile):
    top_k: int = Field(default=8, ge=1, le=15)


class ClarifyRequest(CitizenProfile):
    text: str | None = None


class BenefitsJourneyRequest(CitizenProfile):
    top_k: int = Field(default=8, ge=1, le=15)


def _eligibility_state(status: str | None) -> str:
    if status in {"relevant"}:
        return "MATCH"
    if status in {"likely_not_eligible", "not_relevant"}:
        return "MISMATCH"
    return "UNKNOWN"


def _clarifying_questions(profile: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("age", "What is your age?"),
        ("state", "Which Indian state or union territory do you live in?"),
        ("annual_household_income_inr", "What is your annual household income?"),
        ("category", "What is your social category, if applicable?"),
        ("occupation", "What best describes your current occupation or status?"),
        ("goal", "What kind of support are you looking for?"),
    ]
    return [
        {"field": field, "question": question}
        for field, question in checks
        if profile.get(field) in (None, "", [])
    ]


def _journey_from_recommendations(profile: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    recommendations = result.get("recommendations") or []
    steps = []
    for index, item in enumerate(recommendations, start=1):
        status = item.get("eligibility_status")
        missing = item.get("missing_information") or []
        source = item.get("official_source_url") or item.get("official_source")
        steps.append(
            {
                "step": index,
                "scheme_name": item.get("scheme_name"),
                "eligibility_status": status,
                "eligibility_state": _eligibility_state(status),
                "why_it_matters": item.get("relevance_explanation"),
                "benefits": item.get("benefits"),
                "documents": item.get("required_documents") or [],
                "missing_information": missing,
                "next_action": (
                    "Review the official source and prepare the listed documents."
                    if source
                    else "Ask for official source verification before applying."
                ),
                "official_source_url": source,
                "source_verification": item.get("source_verification"),
            }
        )
    return {
        "profile": profile,
        "journey": steps,
        "summary": {
            "total_options": len(steps),
            "match_count": sum(1 for step in steps if step["eligibility_state"] == "MATCH"),
            "unknown_count": sum(1 for step in steps if step["eligibility_state"] == "UNKNOWN"),
            "mismatch_count": sum(1 for step in steps if step["eligibility_state"] == "MISMATCH"),
        },
        "retrieval": result.get("retrieval"),
        "notice": result.get("notice"),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "retrieval": "live_web_search",
        "provider": "tavily",
        "stores_schemes": False,
    }


@app.post("/recommend")
def recommend(payload: RecommendRequest) -> dict[str, Any]:
    profile = payload.model_dump(exclude={"top_k"})
    try:
        return recommend_for_profile(profile, top_k=payload.top_k)
    except LiveSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Live search failed",
                "message": str(exc),
                "fallback_used": False,
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "Service configuration error", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "Could not interpret live scheme information", "message": str(exc)},
        ) from exc


@app.post("/clarify")
def clarify(payload: ClarifyRequest) -> dict[str, Any]:
    profile = normalize_profile(payload.model_dump())
    if payload.text:
        profile["other_relevant_information"] = payload.text
        lowered = payload.text.lower()
        if "student" in lowered and not profile.get("occupation"):
            profile["occupation"] = "Student"
            profile["student_status"] = "Yes"
        if "farmer" in lowered and not profile.get("occupation"):
            profile["occupation"] = "Farmer"
            profile["farmer_status"] = "Yes"
        if "unemployed" in lowered:
            profile["employment_status"] = "Unemployed"
        if "retired" in lowered:
            profile["employment_status"] = "Retired"
        if "disabled" in lowered or "disability" in lowered:
            profile["disability_status"] = "Yes"
    return {
        "profile": profile,
        "missing_questions": _clarifying_questions(profile),
        "ready_for_recommendation": len(_clarifying_questions(profile)) == 0,
    }


@app.post("/benefits/journey")
def benefits_journey(payload: BenefitsJourneyRequest) -> dict[str, Any]:
    profile = payload.model_dump(exclude={"top_k"})
    try:
        result = recommend_for_profile(profile, top_k=payload.top_k)
        return _journey_from_recommendations(normalize_profile(profile), result)
    except LiveSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Live search failed",
                "message": str(exc),
                "fallback_used": False,
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "Service configuration error", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "Could not interpret live scheme information", "message": str(exc)},
        ) from exc


@app.get("/schemes/search")
def schemes_search(
    q: str = Query(..., min_length=2, description="Live search query"),
    top_k: int = Query(default=8, ge=1, le=15),
) -> dict[str, Any]:
    try:
        return search_schemes(q, top_k=top_k)
    except LiveSearchError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Live search failed",
                "message": str(exc),
                "fallback_used": False,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
