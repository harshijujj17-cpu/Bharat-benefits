"""Gemini-based transcription with a provider-friendly function boundary.

Transcription pipeline:
  1. Try ``gemini-3.5-transcribe`` (dedicated STT model, audio-only, no text prompt).
  2. Fall back to multimodal models with a text prompt + audio part.

Refusal detection:
  Multimodal models occasionally return "I cannot access audio files…" instead of a
  transcript.  These responses are detected and rejected so the fallback chain
  continues correctly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ─────────────────────────────────────────────────────────────────
# Languages
# ─────────────────────────────────────────────────────────────────
SUPPORTED_LANGUAGES = ("English", "Hindi", "Telugu")

_LANGUAGE_CODES: dict[str, str] = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Telugu": "te-IN",
}

# ─────────────────────────────────────────────────────────────────
# Model strategy
# ─────────────────────────────────────────────────────────────────
# Primary: dedicated transcription model (audio-only input).
_TRANSCRIBE_MODEL = "gemini-3.5-transcribe"

# Multimodal fallbacks: accept a text prompt + audio part.
# gemini-2.5-flash is DEPRECATED (404) — do NOT use.
_MULTIMODAL_FALLBACKS = (
    "gemini-3.1-flash-lite", # Verified audio-capable, lightweight
    "gemini-3.5-flash",      # Second fallback
)


# Kept for backwards compatibility with code that imports STT_FALLBACK_MODELS
STT_FALLBACK_MODELS = _MULTIMODAL_FALLBACKS
DEFAULT_MODEL_NAME = _TRANSCRIBE_MODEL

# ─────────────────────────────────────────────────────────────────
# MIME normalisation
# ─────────────────────────────────────────────────────────────────
# Streamlit st.audio_input (sample_rate=16000) returns audio/wav.
# Some browsers may return audio/webm; normalise to Gemini-supported values.
_MIME_ALIASES: dict[str, str] = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/webm;codecs=opus": "audio/webm",
    "audio/ogg;codecs=opus": "audio/ogg",
    "audio/mpeg": "audio/mpeg",
    "audio/mp4": "audio/mp4",
}

# Phrases that indicate a model refused to process the audio (not a real transcript)
_REFUSAL_PHRASES = (
    "i cannot",
    "i can't",
    "i am unable",
    "i'm unable",
    "unable to listen",
    "unable to access",
    "unable to transcribe",
    "cannot access",
    "cannot listen",
    "cannot hear",
    "cannot process audio",
    "please upload",
    "please provide",
    "no audio",
    "didn't come through",
    "did not come through",
    "provide the audio",
    "attach the audio",
)


class SpeechToTextError(RuntimeError):
    """Raised when microphone audio cannot be transcribed."""


# ─────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────

def _get_client() -> Any:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SpeechToTextError(
            "GEMINI_API_KEY is not set. Add it to Government-Scheme-Agent/.env.\n"
            "Get a free key at https://aistudio.google.com/app/apikey"
        )
    logger.debug("Loaded GEMINI_API_KEY (length=%d)", len(api_key))
    return genai.Client(api_key=api_key)


def _normalize_mime(mime_type: str) -> str:
    """Normalize MIME type to a Gemini-supported value."""
    full_lower = mime_type.strip().lower()
    base = full_lower.split(";")[0].strip()
    return (
        _MIME_ALIASES.get(full_lower)
        or _MIME_ALIASES.get(base)
        or base
        or "audio/wav"
    )


def _is_refusal(text: str) -> bool:
    """Return True if the model response is a refusal, not a transcript."""
    lower = text.lower()
    return any(phrase in lower for phrase in _REFUSAL_PHRASES)


def _try_transcribe_model(
    client: Any,
    audio_bytes: bytes,
    mime_type: str,
    language: str,  # noqa: ARG001  (reserved for future language-config support)
) -> str | None:
    """Try the dedicated gemini-3.5-transcribe model.

    This model accepts audio only (no text prompt).  Returns ``None`` on empty
    response (silence / very short clip) so the caller falls through to
    multimodal fallbacks.
    """
    logger.debug(
        "Trying dedicated STT model=%s  audio=%.1f kB  mime=%s  language=%s",
        _TRANSCRIBE_MODEL,
        len(audio_bytes) / 1024,
        mime_type,
        language,
    )
    try:
        response = client.models.generate_content(
            model=_TRANSCRIBE_MODEL,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            ],
        )
        transcript = (response.text or "").strip()
        if transcript:
            logger.info(
                "Transcription succeeded with dedicated model=%s", _TRANSCRIBE_MODEL
            )
            return transcript
        logger.debug(
            "Dedicated model %s returned empty response (silence or very short audio)",
            _TRANSCRIBE_MODEL,
        )
        return None
    except Exception as exc:
        logger.warning(
            "Dedicated STT model %s failed: %s: %s",
            _TRANSCRIBE_MODEL,
            type(exc).__name__,
            exc,
        )
        return None


def _try_multimodal_model(
    client: Any,
    model: str,
    audio_bytes: bytes,
    mime_type: str,
    language: str,
) -> str | None:
    """Try a multimodal model with a text prompt + audio part.

    Returns the transcript on success, ``None`` on empty/refusal, and raises on
    hard API errors so the caller can log them and continue to the next candidate.
    """
    prompt = (
        f"Transcribe the speech in this audio recording in {language}. "
        "Output ONLY the exact words spoken. "
        "Do not translate, summarise, add punctuation beyond what was spoken, "
        "or add any commentary."
    )
    logger.debug(
        "Trying multimodal model=%s  audio=%.1f kB  mime=%s  language=%s",
        model,
        len(audio_bytes) / 1024,
        mime_type,
        language,
    )
    response = client.models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
        ],
    )
    transcript = (response.text or "").strip()
    if not transcript:
        logger.debug("Model %s returned empty response", model)
        return None
    if _is_refusal(transcript):
        logger.warning(
            "Model %s returned a refusal instead of a transcript: %r",
            model,
            transcript[:200],
        )
        return None
    logger.info("Transcription succeeded with multimodal model=%s", model)
    return transcript


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str,
    language: str = "English",
    client: Any | None = None,
    model_name: str | None = None,
) -> str:
    """Transcribe a microphone recording, preserving its selected language.

    Tries the dedicated ``gemini-3.5-transcribe`` model first, then falls back
    to multimodal models (``gemini-3.1-flash-lite``, ``gemini-3.5-flash``).
    Refusal responses are detected and skipped.

    The actual API error is always included in ``SpeechToTextError`` so that
    the Streamlit UI can display it for debugging.

    Parameters
    ----------
    audio_bytes:
        Raw bytes from ``st.audio_input().getvalue()``.
    mime_type:
        MIME type from Streamlit (e.g. ``"audio/wav"``).
    language:
        One of ``SUPPORTED_LANGUAGES`` (English, Hindi, Telugu).
    client:
        Optional pre-built ``genai.Client`` (useful in tests).
    model_name:
        Override primary model (skips ``gemini-3.5-transcribe``).
    """
    if not audio_bytes:
        raise SpeechToTextError(
            "The microphone recording is empty. Please record again."
        )
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language}'. "
            f"Choose one of: {SUPPORTED_LANGUAGES}."
        )

    normalized_mime = _normalize_mime(mime_type)
    logger.info(
        "Transcription request: %.1f kB | original_mime=%s | normalized_mime=%s | language=%s",
        len(audio_bytes) / 1024,
        mime_type,
        normalized_mime,
        language,
    )

    if client is None:
        client = _get_client()

    # ── 1. Dedicated transcribe model ──────────────────────────────────────
    if not model_name:
        result = _try_transcribe_model(client, audio_bytes, normalized_mime, language)
        if result:
            return result

    # ── 2. Multimodal fallbacks ─────────────────────────────────────────────
    if model_name:
        candidates = [model_name] + [
            m for m in _MULTIMODAL_FALLBACKS if m != model_name
        ]
    else:
        candidates = list(_MULTIMODAL_FALLBACKS)

    last_error: Exception | None = None
    for cand in candidates:
        try:
            result = _try_multimodal_model(
                client, cand, audio_bytes, normalized_mime, language
            )
            if result:
                return result
            # Empty or refusal — try next model
        except Exception as exc:
            logger.warning(
                "Multimodal model %s raised %s: %s",
                cand,
                type(exc).__name__,
                exc,
            )
            last_error = exc
            continue

    # ── 3. All models exhausted ─────────────────────────────────────────────
    if last_error:
        detail = f"{type(last_error).__name__}: {last_error}"
    else:
        detail = (
            "All models returned empty or refused to transcribe. "
            "This can happen with very short recordings or silence — "
            "please speak clearly for at least 2 seconds and try again."
        )

    raise SpeechToTextError(
        "Speech transcription failed after trying all available models.\n\n"
        f"Error detail: {detail}\n\n"
        "Troubleshooting:\n"
        "  • Make sure your microphone is working and not muted.\n"
        "  • Speak clearly for at least 2–3 seconds.\n"
        "  • Check that GEMINI_API_KEY in .env is valid.\n"
        "  • Check your internet connection."
    )