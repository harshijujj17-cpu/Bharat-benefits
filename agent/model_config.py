"""Central Gemini model + timeout configuration.

Single source of truth for model names and upstream timeouts so every module
(scheme extraction, eligibility reasoning, query building, profile parsing)
uses the same configured model instead of drifting hard-coded values.

Environment overrides
---------------------
``GEMINI_MODEL``            Primary model id (default ``gemini-3.1-flash-lite``).
``GEMINI_FALLBACK_MODELS``  Comma-separated fallbacks tried after the primary.
``GEMINI_TIMEOUT_MS``       Per-request Gemini timeout in milliseconds.
``TAVILY_TIMEOUT_SECONDS``  Per-request Tavily search timeout in seconds.

Model ids must be valid for the configured ``GEMINI_API_KEY``. Failures are
logged (never silently swallowed) and the last error is raised if every
candidate fails.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.1-flash-lite"
# Fallbacks are model ids verified reachable for the configured key. Retired ids
# (e.g. gemini-2.0-flash / gemini-2.5-flash return 404) are intentionally absent.
DEFAULT_FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest")
DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_TAVILY_TIMEOUT_SECONDS = 20.0


def get_model_name() -> str:
    """Return the configured primary Gemini model id."""
    return (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()


def get_fallback_models() -> tuple[str, ...]:
    """Return configured fallback model ids (defaults if unset)."""
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    if raw:
        return tuple(model.strip() for model in raw.split(",") if model.strip())
    return DEFAULT_FALLBACK_MODELS


def get_timeout_ms() -> int:
    """Return the Gemini request timeout in milliseconds."""
    raw = os.getenv("GEMINI_TIMEOUT_MS")
    if not raw:
        return DEFAULT_TIMEOUT_MS
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid GEMINI_TIMEOUT_MS=%r; using %d", raw, DEFAULT_TIMEOUT_MS)
        return DEFAULT_TIMEOUT_MS


def get_tavily_timeout_seconds() -> float:
    """Return the Tavily search timeout in seconds."""
    raw = os.getenv("TAVILY_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TAVILY_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "Invalid TAVILY_TIMEOUT_SECONDS=%r; using %s", raw, DEFAULT_TAVILY_TIMEOUT_SECONDS
        )
        return DEFAULT_TAVILY_TIMEOUT_SECONDS


def ordered_models(model_name: str | None = None) -> list[str]:
    """Primary model followed by de-duplicated fallbacks."""
    primary = (model_name or get_model_name()).strip()
    ordered = [primary] if primary else []
    for model in get_fallback_models():
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def build_client(api_key: str | None = None) -> Any:
    """Create a ``genai.Client`` with the configured upstream timeout."""
    from agent.secrets import get_api_key

    key = api_key or get_api_key()
    return genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=get_timeout_ms()),
    )


def generate_with_fallback(
    client: Any,
    contents: Any,
    *,
    config: Any,
    model_name: str | None = None,
    purpose: str = "gemini",
) -> Any:
    """Call ``generate_content`` across primary + fallback models.

    Each failure is logged with the model id and error type. Returns the first
    response that has non-empty text. Raises the last error if every candidate
    fails, so model/API problems surface instead of being silently ignored.
    """
    models = ordered_models(model_name)
    if not models:
        raise RuntimeError(f"{purpose}: no Gemini model configured.")

    last_error: Exception | None = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 - logged and re-raised below
            last_error = exc
            logger.warning(
                "%s: model %r failed (%s: %s)", purpose, model, type(exc).__name__, exc
            )
            continue
        if getattr(response, "text", None):
            return response
        logger.warning("%s: model %r returned empty text; trying next candidate", purpose, model)

    if last_error:
        raise last_error
    raise ValueError(
        f"{purpose}: every configured model returned an empty response ({models})."
    )


__all__ = [
    "DEFAULT_MODEL",
    "get_model_name",
    "get_fallback_models",
    "get_timeout_ms",
    "get_tavily_timeout_seconds",
    "ordered_models",
    "build_client",
    "generate_with_fallback",
]
