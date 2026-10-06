"""FastAPI service for live government-scheme recommendations.

Design notes
------------
* One live pipeline per request. ``/recommend`` runs Tavily + Gemini exactly
  once and returns the benefits journey derived from that same result, so the
  UI never needs a second call.
* ``/benefits/journey`` is kept for API compatibility. When the caller already
  has ``recommendations`` it reshapes them without any live search; otherwise it
  runs the pipeline once.
* No static scheme fallback: if live retrieval fails the API returns a JSON
  error (503) and never invents schemes.
* Paid endpoints are rate-limited per client and CORS is restricted to the
  configured frontend origin(s). API keys are never returned by any endpoint.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from agent.provider_errors import (
    ERROR_INTERNAL,
    ERROR_INVALID_REQUEST,
    ERROR_UPSTREAM,
    MESSAGE_INTERNAL,
    MESSAGE_INVALID_REQUEST,
    MESSAGE_UPSTREAM,
    classify_provider_error,
)
from agent.model_config import get_model_name
from agent.pipeline import recommend_for_profile, search_schemes
from agent.profile_extractor import extract_profile
from agent.profile_normalize import normalize_profile
from rag.live_retriever import LiveSearchError

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────

def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# Restrict CORS to the deployed frontend origin(s). Override with CORS_ORIGINS
# (comma-separated). Set to "*" only if you deliberately want a public API.
CORS_ORIGINS = _csv_env(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


app = FastAPI(
    title="Government Scheme Recommendation API",
    description=(
        "Recommends current Indian government schemes using live web retrieval "
        "from official sources. Scheme records are not stored locally."
    ),
    version="2.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── Simple in-memory rate limiter (protects paid Tavily/Gemini calls) ─────

_rate_buckets: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()


def _client_id(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """Best-effort fixed-window rate limit per client for paid endpoints."""
    if not RATE_LIMIT_ENABLED:
        return
    client_id = _client_id(request)
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[client_id]
        while bucket and (now - bucket[0]) >= RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_REQUESTS:
            retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": (
                        f"Too many requests. Limit is {RATE_LIMIT_REQUESTS} per "
                        f"{int(RATE_LIMIT_WINDOW_SECONDS)}s."
                    ),
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a bare 500; always return a JSON error shape."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred while processing the request.",
        },
    )


# ── Request models ───────────────────────────────────────────────────────

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
    need: str | None = None  # life-event/need mode: mapped into goal when goal is absent


class RecommendRequest(CitizenProfile):
    top_k: int = Field(default=8, ge=1, le=15)


class ClarifyRequest(CitizenProfile):
    text: str | None = None


class BenefitsJourneyRequest(CitizenProfile):
    top_k: int = Field(default=8, ge=1, le=15)
    # Optional pre-computed pipeline output. When provided, the endpoint
    # reshapes it into a journey WITHOUT running another live search.
    recommendations: list[dict[str, Any]] | None = None
    retrieval: dict[str, Any] | None = None
    notice: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────

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


def _map_pipeline_errors(exc: Exception) -> HTTPException:
    """Translate known pipeline errors into structured JSON HTTP errors.

    Provider failures (quota, timeout, upstream 5xx) get explicit codes and
    never leak keys, stack traces, or raw provider payloads. Unknown
    exceptions become a generic 500. No static fallback is used.
    """
    classified = classify_provider_error(exc)
    if classified is not None:
        logger.warning("Provider failure (%s): %s", classified["error"], type(exc).__name__)
        return HTTPException(
            status_code=classified["status"],
            detail={
                "error": classified["error"],
                "provider": classified["provider"],
                "message": classified["message"],
            },
        )
    if isinstance(exc, ValueError):
        if "empty" in str(exc).lower():
            return HTTPException(
                status_code=400,
                detail={"error": ERROR_INVALID_REQUEST, "provider": "client", "message": MESSAGE_INVALID_REQUEST},
            )
        # Gemini produced unusable output: treat as an upstream provider issue.
        logger.warning("Provider returned unusable output: %s", type(exc).__name__)
        return HTTPException(
            status_code=502,
            detail={"error": ERROR_UPSTREAM, "provider": "gemini", "message": MESSAGE_UPSTREAM},
        )
    if isinstance(exc, RuntimeError):
        logger.error("Service configuration error: %s", type(exc).__name__)
        return HTTPException(
            status_code=500,
            detail={"error": ERROR_INTERNAL, "provider": "server", "message": MESSAGE_INTERNAL},
        )
    logger.exception("Unexpected pipeline error")
    return HTTPException(
        status_code=500,
        detail={"error": ERROR_INTERNAL, "provider": "server", "message": MESSAGE_INTERNAL},
    )


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness + config presence. Never returns secret values."""
    gemini_present = bool(os.getenv("GEMINI_API_KEY", "").strip())
    tavily_present = bool(os.getenv("TAVILY_API_KEY", "").strip())
    return {
        "status": "ok" if (gemini_present and tavily_present) else "degraded",
        "retrieval": "live_web_search",
        "provider": "tavily",
        "stores_schemes": False,
        "config": {
            "gemini_api_key_present": gemini_present,
            "tavily_api_key_present": tavily_present,
            "model": get_model_name(),
            "rate_limit_enabled": RATE_LIMIT_ENABLED,
            "cors_origins": CORS_ORIGINS,
        },
    }


@app.post("/recommend")
def recommend(payload: RecommendRequest, _: None = Depends(rate_limit)) -> dict[str, Any]:
    profile = payload.model_dump(exclude={"top_k"})
    # Need-mode: a life-situation need becomes the search goal when no goal is set.
    if profile.get("need") and not profile.get("goal"):
        profile["goal"] = profile["need"]
    if profile.get("need") and not profile.get("current_situation"):
        profile["current_situation"] = profile["need"]
    try:
        result = recommend_for_profile(profile, top_k=payload.top_k)
    except Exception as exc:  # noqa: BLE001 - mapped to a JSON error below
        raise _map_pipeline_errors(exc) from exc

    # Derive the journey from THIS result — no second live search.
    result["journey"] = _journey_from_recommendations(normalize_profile(profile), result)
    return result


@app.post("/clarify")
def clarify(payload: ClarifyRequest, _: None = Depends(rate_limit)) -> dict[str, Any]:
    base = normalize_profile(payload.model_dump(exclude={"text"}))
    profile_source = "structured"

    if payload.text and payload.text.strip():
        base["other_relevant_information"] = payload.text
        profile_source = "llm"
        try:
            # Canonical extraction: the same Gemini logic used across the system.
            extracted = extract_profile(payload.text.strip())
            for key, value in (extracted or {}).items():
                # Preserve unknowns: only fill blanks, never overwrite with None.
                if value is not None and base.get(key) in (None, "", []):
                    base[key] = value
        except Exception as exc:  # noqa: BLE001 - degrade, but surface the reason
            logger.warning(
                "/clarify LLM extraction failed (%s: %s); returning unstructured profile",
                type(exc).__name__,
                exc,
            )
            profile_source = "fallback"

    profile = normalize_profile(base)
    missing = _clarifying_questions(profile)
    return {
        "profile": profile,
        "profile_source": profile_source,
        "missing_questions": missing,
        "ready_for_recommendation": len(missing) == 0,
    }


@app.post("/benefits/journey")
def benefits_journey(
    payload: BenefitsJourneyRequest, _: None = Depends(rate_limit)
) -> dict[str, Any]:
    profile = normalize_profile(
        payload.model_dump(exclude={"top_k", "recommendations", "retrieval", "notice"})
    )

    # Compatibility path: reshape caller-supplied recommendations, no live search.
    if payload.recommendations is not None:
        return _journey_from_recommendations(
            profile,
            {
                "recommendations": payload.recommendations,
                "retrieval": payload.retrieval,
                "notice": payload.notice,
            },
        )

    raw_profile = payload.model_dump(exclude={"top_k", "recommendations", "retrieval", "notice"})
    try:
        result = recommend_for_profile(raw_profile, top_k=payload.top_k)
    except Exception as exc:  # noqa: BLE001 - mapped to a JSON error below
        raise _map_pipeline_errors(exc) from exc
    return _journey_from_recommendations(profile, result)


@app.get("/schemes/search")
def schemes_search(
    q: str = Query(..., min_length=2, description="Live search query"),
    top_k: int = Query(default=8, ge=1, le=15),
    _: None = Depends(rate_limit),
) -> dict[str, Any]:
    try:
        return search_schemes(q, top_k=top_k)
    except LiveSearchError as exc:
        classified = classify_provider_error(exc)
        if classified is not None:
            raise HTTPException(
                status_code=classified["status"],
                detail={
                    "error": classified["error"],
                    "provider": classified["provider"],
                    "message": classified["message"],
                    "fallback_used": False,
                },
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={"error": ERROR_UPSTREAM, "provider": "tavily", "message": MESSAGE_UPSTREAM, "fallback_used": False},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": ERROR_INVALID_REQUEST, "provider": "client", "message": MESSAGE_INVALID_REQUEST},
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise _map_pipeline_errors(exc) from exc
