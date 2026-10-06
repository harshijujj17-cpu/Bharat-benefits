"""Explicit classification of provider (Gemini/Tavily) failures.

Maps raw provider exceptions to a small, stable set of structured error
payloads so the API can distinguish quota, timeouts, upstream 5xx failures,
and genuine server bugs — without leaking API keys, stack traces, or raw
provider messages to clients.
"""

from __future__ import annotations

import re
from typing import Any

from rag.live_retriever import LiveSearchError

ERROR_QUOTA = "provider_quota_exhausted"
ERROR_TIMEOUT = "provider_timeout"
ERROR_UPSTREAM = "provider_upstream_error"
ERROR_INVALID_REQUEST = "invalid_request"
ERROR_INTERNAL = "internal_server_error"

MESSAGE_QUOTA = "The AI provider quota is temporarily exhausted. Please try again later."
MESSAGE_TIMEOUT = "The upstream provider did not respond in time. Please try again."
MESSAGE_UPSTREAM = "The upstream provider returned an error. Please try again later."
MESSAGE_INVALID_REQUEST = "The request was invalid."
MESSAGE_INTERNAL = "An unexpected error occurred."

_QUOTA_RE = re.compile(r"resource_exhausted|quota|rate[\s_-]?limit|\b429\b", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"timed?\s?out|timeout|deadline[\s_-]?exceeded|deadlineexceeded", re.IGNORECASE)
_UPSTREAM_5XX_RE = re.compile(r"\b50[0-4]\b|service unavailable|bad gateway|internal error|unavailable", re.IGNORECASE)
_TAVILY_RE = re.compile(r"tavily", re.IGNORECASE)


def _provider_for(exc: BaseException, text: str) -> str:
    if isinstance(exc, LiveSearchError) or _TAVILY_RE.search(text):
        return "tavily"
    return "gemini"


def classify_provider_error(exc: BaseException) -> dict[str, Any] | None:
    """Classify a provider exception into a structured error payload.

    Returns ``{"status", "error", "provider", "message"}`` or ``None`` when
    the exception is not recognizably a provider failure. Messages are fixed
    strings — raw exception text is never exposed to clients.
    """
    text = f"{type(exc).__name__}: {exc}"
    provider = _provider_for(exc, text)

    if _QUOTA_RE.search(text):
        return {"status": 503, "error": ERROR_QUOTA, "provider": provider, "message": MESSAGE_QUOTA, "category": "provider_rate_limit"}
    if _TIMEOUT_RE.search(text) or isinstance(exc, TimeoutError):
        return {"status": 504, "error": ERROR_TIMEOUT, "provider": provider, "message": MESSAGE_TIMEOUT, "category": "provider_timeout"}
    if "401" in text or "403" in text or "unauthorized" in text or "invalid api key" in text or "api key not valid" in text:
        return {"status": 502, "error": ERROR_UPSTREAM, "provider": provider, "message": MESSAGE_UPSTREAM, "category": "provider_auth_error"}
    if _UPSTREAM_5XX_RE.search(text):
        return {"status": 502, "error": ERROR_UPSTREAM, "provider": provider, "message": MESSAGE_UPSTREAM, "category": "provider_unavailable"}
    if isinstance(exc, LiveSearchError):
        return {"status": 502, "error": ERROR_UPSTREAM, "provider": "tavily", "message": MESSAGE_UPSTREAM, "category": "transient_provider_error"}
    return None


def provider_error_detail(exc: BaseException) -> dict[str, Any] | None:
    """Return the ``detail`` dict for a structured HTTPException, or None."""
    classified = classify_provider_error(exc)
    if classified is None:
        return None
    return {
        "error": classified["error"],
        "provider": classified["provider"],
        "message": classified["message"],
        "category": classified.get("category"),
    }


__all__ = [
    "ERROR_QUOTA",
    "ERROR_TIMEOUT",
    "ERROR_UPSTREAM",
    "ERROR_INVALID_REQUEST",
    "ERROR_INTERNAL",
    "classify_provider_error",
    "provider_error_detail",
]
