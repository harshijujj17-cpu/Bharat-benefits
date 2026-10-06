"""Bounded retry with exponential backoff + jitter for transient provider failures."""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TRANSIENT_HINTS = (
    "429",
    "rate limit",
    "resource_exhausted",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "deadline",
    "connection",
    "temporarily",
    "unavailable",
    "econnreset",
    "getaddrinfo",
    "socket",
)

_PERMANENT_HINTS = (
    "invalid api key",
    "api key not valid",
    "unauthorized",
    "forbidden",
    "permission denied",
    "validation",
    "bad request",
    "400",
)


def classify_attempt(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(h in text for h in _PERMANENT_HINTS):
        # Permanent wins only if it is not also a 429/quota case.
        if "429" not in text and "resource_exhausted" not in text and "quota" not in text:
            return "permanent"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if any(h in text for h in ("timeout", "timed out", "deadline")):
        return "timeout"
    if "429" in text or "rate limit" in text or "resource_exhausted" in text or "quota" in text:
        return "provider_rate_limit"
    if any(h in text for h in _TRANSIENT_HINTS):
        return "transient"
    return "unknown"


def is_retryable(exc: BaseException) -> bool:
    return classify_attempt(exc) in {"transient", "timeout", "provider_rate_limit"}


def with_retries(
    func: Callable[[], T],
    *,
    provider: str,
    operation: str,
    max_retries: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
) -> T:
    """Run *func*, retrying transient failures with exp backoff + jitter.

    No retries for permanent errors. Total extra delay stays modest
    (<= ~ max_delay * (2^n-1) + jitter) so this fits a free/Render budget.
    """
    attempt = 0
    started = time.monotonic()
    while True:
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            category = classify_attempt(exc)
            if attempt > max_retries or not is_retryable(exc):
                logger.warning(
                    "provider=%s operation=%s attempt=%d category=%s elapsed_ms=%d result=giveup",
                    provider, operation, attempt, category, int((time.monotonic() - started) * 1000),
                )
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1))) + random.uniform(0, base_delay)
            logger.info(
                "provider=%s operation=%s attempt=%d category=%s elapsed_ms=%d retry_in=%.2fs",
                provider, operation, attempt, category, int((time.monotonic() - started) * 1000), delay,
            )
            time.sleep(delay)
