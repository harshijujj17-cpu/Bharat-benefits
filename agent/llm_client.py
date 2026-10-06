"""LLM provider abstraction.

The agent may use Gemini (default) or any OpenAI-compatible chat endpoint,
selected entirely through environment variables:

    LLM_PROVIDER            "gemini" (default) | "openai_compatible"
    LLM_MODEL               primary model id (defaults to GEMINI_MODEL/gemini-3.1-flash-lite)
    LLM_FALLBACK_MODELS     comma-separated fallback model ids
    LLM_API_KEY             key for openai_compatible providers (never hard-coded)
    LLM_BASE_URL            base URL for openai_compatible providers
    GEMINI_MODEL / GEMINI_FALLBACK_MODELS / GEMINI_TIMEOUT_MS (existing)

One provider/model set is used per request with controlled fallback across
that provider's configured models only. No static scheme data, no caching.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


def get_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()


def get_primary_model() -> str:
    generic = (os.getenv("LLM_MODEL") or "").strip()
    if generic:
        return generic
    return (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()


def get_fallback_models() -> tuple[str, ...]:
    raw = os.getenv("LLM_FALLBACK_MODELS")
    if raw:
        return tuple(m.strip() for m in raw.split(",") if m.strip())
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    if raw:
        return tuple(m.strip() for m in raw.split(",") if m.strip())
    return (DEFAULT_GEMINI_MODEL,)


def ordered_models() -> list[str]:
    ordered = [get_primary_model()]
    for m in get_fallback_models():
        if m not in ordered:
            ordered.append(m)
    return ordered


class LLMResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def _gemini_generate(prompt: str, *, system_instruction: str | None, response_schema: dict | None,
                     temperature: float, model_name: str, purpose: str) -> LLMResponse:
    from google import genai
    from google.genai import types

    from agent import model_config
    from agent.secrets import get_gemini_api_key

    client = genai.Client(api_key=get_gemini_api_key(), http_options=types.HttpOptions(timeout=model_config.get_timeout_ms()))
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=response_schema,
        temperature=temperature,
    )
    response = client.models.generate_content(model=model_name, contents=prompt, config=config)
    return LLMResponse(response.text or "")


def _openai_compatible_generate(prompt: str, *, system_instruction: str | None, response_schema: dict | None,
                                temperature: float, model_name: str, purpose: str) -> LLMResponse:
    import urllib.request

    key = (os.getenv("LLM_API_KEY") or "").strip()
    base = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    if not key:
        raise RuntimeError("LLM_API_KEY is not set for the openai_compatible provider.")
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    text = payload["choices"][0]["message"]["content"]
    return LLMResponse(text or "")


def generate(prompt: str, *, system_instruction: str | None = None, response_schema: dict | None = None,
             temperature: float = 0.0, purpose: str = "llm", model_name: str | None = None) -> LLMResponse:
    """Generate JSON text with the configured provider, trying fallback models once each."""
    provider = get_provider()
    models = [model_name] if model_name else ordered_models()
    if not models:
        raise RuntimeError(f"{purpose}: no LLM model configured.")

    last_error: Exception | None = None
    for model in models:
        try:
            if provider == "gemini":
                result = _gemini_generate(prompt, system_instruction=system_instruction,
                                          response_schema=response_schema, temperature=temperature,
                                          model_name=model, purpose=purpose)
            elif provider == "openai_compatible":
                result = _openai_compatible_generate(prompt, system_instruction=system_instruction,
                                                     response_schema=response_schema, temperature=temperature,
                                                     model_name=model, purpose=purpose)
            else:
                raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}")
        except Exception as exc:  # noqa: BLE001 - logged, try fallback model
            last_error = exc
            logger.warning("%s: provider %s model %r failed (%s)", purpose, provider, model, type(exc).__name__)
            continue
        if result.text:
            return result
        logger.warning("%s: model %r returned empty text; trying next candidate", purpose, model)

    if last_error:
        raise last_error
    raise ValueError(f"{purpose}: every configured model returned an empty response ({models}).")


__all__ = [
    "get_provider",
    "get_primary_model",
    "get_fallback_models",
    "ordered_models",
    "generate",
    "LLMResponse",
]
