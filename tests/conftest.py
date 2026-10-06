"""Shared pytest configuration.

Sets dummy secrets and disables rate limiting BEFORE ``api.main`` is imported
(the test fixtures import it lazily), so the suite never uses real API keys and
never trips the per-client request guard.
"""

import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
