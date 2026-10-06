"""Provider error-classification tests.

Verifies that Gemini/Tavily failures surface as explicit, structured JSON
errors (quota -> 503, timeout -> 504, upstream 5xx -> 502, unexpected -> 500)
and that responses never leak keys, provider raw text, or stack traces, and
never fall back to static/fabricated schemes.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rag.live_retriever import LiveSearchError

PAYLOAD = {"age": 20, "education": "B.Tech", "state": "Telangana", "category": "OBC"}


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _raise(monkeypatch, exc: Exception):
    def boom(profile, top_k=8):
        raise exc

    monkeypatch.setattr("api.main.recommend_for_profile", boom)


def _body_text(response) -> str:
    return json.dumps(response.json())


def _assert_no_leak(response) -> None:
    text = _body_text(response)
    assert "test-gemini" not in text
    assert "test-tavily" not in text
    assert "Traceback" not in text
    assert "recommendation_failed" not in text


def test_gemini_resource_exhausted_maps_to_503_quota(monkeypatch, api_client):
    _raise(monkeypatch, Exception(
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota'}}"
    ))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "provider_quota_exhausted"
    assert detail["provider"] == "gemini"
    assert "quota" in detail["message"].lower()
    _assert_no_leak(r)


def test_gemini_timeout_maps_to_504(monkeypatch, api_client):
    _raise(monkeypatch, TimeoutError("Gemini request timed out after 30000ms"))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 504
    detail = r.json()["detail"]
    assert detail["error"] == "provider_timeout"
    assert detail["provider"] == "gemini"
    _assert_no_leak(r)


def test_tavily_timeout_maps_to_504_with_tavily_provider(monkeypatch, api_client):
    _raise(monkeypatch, LiveSearchError("Live search failed: Tavily request timed out"))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 504
    detail = r.json()["detail"]
    assert detail["error"] == "provider_timeout"
    assert detail["provider"] == "tavily"
    _assert_no_leak(r)


def test_tavily_upstream_5xx_maps_to_502(monkeypatch, api_client):
    _raise(monkeypatch, LiveSearchError("Live search failed: HTTP 502 Bad Gateway from upstream"))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "provider_upstream_error"
    assert detail["provider"] == "tavily"
    _assert_no_leak(r)


def test_gemini_upstream_5xx_maps_to_502(monkeypatch, api_client):
    _raise(monkeypatch, Exception("Gemini API returned 503 Service Unavailable"))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "provider_upstream_error"
    assert detail["provider"] == "gemini"
    _assert_no_leak(r)


def test_unexpected_exception_maps_to_500(monkeypatch, api_client):
    _raise(monkeypatch, KeyError("some_internal_field"))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert detail["error"] == "internal_server_error"
    _assert_no_leak(r)
    assert "some_internal_field" not in _body_text(r)


def test_provider_failures_have_no_static_fallback_or_fabricated_schemes(monkeypatch, api_client):
    _raise(monkeypatch, Exception("429 RESOURCE_EXHAUSTED quota exceeded"))
    r = api_client.post("/recommend", json=PAYLOAD)
    body = r.json()
    assert "recommendations" not in body
    assert "schemes" not in body
    assert body["detail"]["error"] == "provider_quota_exhausted"


def test_gemini_invalid_json_maps_to_502_upstream(monkeypatch, api_client):
    _raise(monkeypatch, ValueError("Gemini returned invalid JSON for the recommendations."))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "provider_upstream_error"
    assert detail["provider"] == "gemini"
    _assert_no_leak(r)


def test_empty_query_maps_to_400(monkeypatch, api_client):
    _raise(monkeypatch, ValueError("Search query must not be empty."))
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_request"
    _assert_no_leak(r)


def test_successful_recommend_response_shape(monkeypatch, api_client):
    def fake_recommend(profile, top_k=8):
        return {
            "recommendations": [
                {
                    "scheme_name": "Scholarship X",
                    "eligibility_status": "relevant",
                    "relevance_explanation": "Matches the student profile.",
                    "official_source_url": "https://myscheme.gov.in/schemes/x",
                    "missing_information": [],
                    "source_verification": {"is_official_government_source": True},
                }
            ],
            "retrieval": {
                "mode": "live_web_search",
                "provider": "tavily",
                "cached": False,
                "queries": ["site:myscheme.gov.in Telangana OBC student"],
                "result_count": 3,
                "official_result_count": 3,
                "source_urls": ["https://myscheme.gov.in/schemes/x"],
            },
            "notice": None,
        }

    monkeypatch.setattr("api.main.recommend_for_profile", fake_recommend)
    r = api_client.post("/recommend", json=PAYLOAD)
    assert r.status_code == 200
    payload = r.json()
    assert payload["recommendations"][0]["official_source_url"]
    assert payload["recommendations"][0]["eligibility_status"] == "relevant"
    assert payload["retrieval"]["mode"] == "live_web_search"
    assert payload["retrieval"]["provider"] == "tavily"
    assert payload["retrieval"]["cached"] is False
    assert "journey" in payload
    assert payload["journey"]["profile"]["state"] == "Telangana"
