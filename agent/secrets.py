"""Resolve API keys from environment variables or a local .env file."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")


def get_api_key() -> str:
    """Return the Gemini API key or raise RuntimeError."""
    return get_gemini_api_key()


def get_gemini_api_key() -> str:
    _load_env()
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Add it to the environment or a local .env file."
    )


def get_tavily_api_key() -> str:
    _load_env()
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if key:
        return key
    raise RuntimeError(
        "TAVILY_API_KEY is not set. Add it to the environment or a local .env file."
    )
