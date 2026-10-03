"""Shared helper: resolve GEMINI_API_KEY from Streamlit secrets or .env file.

Import this in every module that needs the API key so there is a single
source of truth for the lookup order:

    1. Streamlit ``st.secrets`` (used in Streamlit Cloud deployment)
    2. Environment variable  ``GEMINI_API_KEY``
    3. ``.env`` file in the project root (local development)
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_api_key() -> str:
    """Return the Gemini API key or raise RuntimeError."""
    # 1. Streamlit secrets (cloud deployment)
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass

    # 2. Env var / .env file
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key

    raise RuntimeError(
        "GEMINI_API_KEY is not set. "
        "Add it to .streamlit/secrets.toml (cloud) or .env (local)."
    )
