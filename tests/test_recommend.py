from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agent.pipeline import recommend_for_profile, search_schemes
from rag.live_retriever import LiveSchemeRetriever, LiveSearchError, SearchHit, rank_hits
from rag.official_sources import is_official_government_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]


OFFICIAL_URL = "https://www.myscheme.gov.in/schemes/post-matric-scholarship-obc"
STATE_URL = "https://telangana.gov.in/scholarships"
NEWS_URL = "https://www.example-news.com/fake-scheme"


def _official_hit() -> SearchHit:
    return SearchHit(
        title="Post Matric Scholarship for OBC Students",
        url=OFFICIAL_URL,
        content=(
            "Government of India Post Matric Scholarship for OBC students. "
            "Eligible students with family income up to Rs 2.5 lakh. "
            "Apply on the National Scholarship Portal."
        ),
        score=0.9,
        official=True,
    )


def _state_hit() -> SearchHit:
    return SearchHit(
        title="Telangana student scholarship",
        url=STATE_URL,
        content="Telangana government scholarship information for students.",
        score=0.7,
        official=True,
    )


def _news_hit() -> SearchHit:
    return SearchHit(
        title="Random blog scheme list",
        url=NEWS_URL,
        content="Unofficial blog listing imaginary schemes.",
        score=0.95,
        official=False,
    )


def _extract_from_hits(hits, profile, **kwargs):
    schemes = []
    for hit in hits:
        if hit.url == NEWS_URL:
            continue
        schemes.append(
            {
                "scheme_name": hit.title,
                "government_department": "Ministry of Social Justice and Empowerment",
                "description": hit.content,
                "eligibility": "OBC students; family income up to Rs 2.5 lakh per year.",
                "benefits": "Tuition fee support as stated on the official page.",
                "application_process": "Apply online through the official portal.",
                "application_url": hit.url,
                "official_source_url": hit.url,
                "important_dates": None,
                "required_documents": ["Aadhaar", "Caste certificate", "Income certificate"],
            }
        )
    return schemes


def _eligibility_payload(profile, schemes, **kwargs):
    income = profile.get("annual_household_income_inr") or profile.get("annual_income") or 0
    recs = []
    for scheme in schemes:
        status = "relevant"
        explanation = (
            f"This live-sourced scheme is relevant because the profile is a "
            f"{profile.get('education')} student in {profile.get('state')} "
            f"({profile.get('category')})."
        )
        missing = []
        if isinstance(income, (int, float)) and income > 250000:
            status = "likely_not_eligible"
            explanation = (
                "The live source states a family-income ceiling of Rs 2.5 lakh. "
                "The profile income is above that limit, so this scheme is likely not eligible."
            )
        if str(profile.get("category", "")).upper() == "GENERAL" and "OBC" in str(scheme.get("eligibility", "")):
            status = "cannot_confirm"
            explanation = (
                "The live source describes an OBC post-matric scholarship. "
                "The profile is General category, so eligibility cannot be confirmed."
            )
            missing.append("An official General-category equivalent scheme was not confirmed from the live sources.")
        recs.append(
            {
                **scheme,
                "scheme_name": scheme["scheme_name"],
                "relevance_explanation": explanation,
                "eligibility_status": status,
                "missing_information": missing,
            }
        )
    return {"recommendations": recs}


@pytest.fixture
def live_retriever():
    calls: list[str] = []

    def search_fn(query: str, **kwargs):
        calls.append(query)
        return [_news_hit(), _official_hit(), _state_hit()]

    retriever = LiveSchemeRetriever(
        search_fn=search_fn,
        extract_fn=_extract_from_hits,
        max_queries=2,
    )
    retriever.calls = calls
    return retriever


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    from api.main import app

    return TestClient(app)


def test_schemes_json_dataset_removed():
    assert not (PROJECT_ROOT / "data" / "schemes.json").exists()
    assert not (PROJECT_ROOT / "rag" / "retriever.py").exists()
    assert not (PROJECT_ROOT / "rag" / "json_retriever.py").exists()
    assert not (PROJECT_ROOT / "app.py").exists()


def test_official_sources_are_prioritized():
    ranked = rank_hits([_news_hit(), _official_hit(), _state_hit()])
    assert ranked[0].official
    assert ranked[0].url == OFFICIAL_URL
    assert ranked[-1].url == NEWS_URL
    assert is_official_government_url(OFFICIAL_URL)
    assert not is_official_government_url(NEWS_URL)


def test_ungrounded_urls_are_dropped():
    retriever = LiveSchemeRetriever(
        search_fn=lambda query, **kwargs: [_official_hit()],
        extract_fn=lambda hits, profile, **kwargs: [
            {
                "scheme_name": "Invented Super Scheme 2099",
                "official_source_url": "https://totally-fake.example/scheme",
                "description": "Hallucinated",
            },
            {
                "scheme_name": "Post Matric Scholarship for OBC Students",
                "official_source_url": OFFICIAL_URL,
                "description": "From live search",
            },
        ],
    )
    schemes = retriever.retrieve_schemes({"state": "Telangana"}, include_llm_queries=False)
    names = [item["scheme_name"] for item in schemes]
    assert "Invented Super Scheme 2099" not in names
    assert names == ["Post Matric Scholarship for OBC Students"]
    assert schemes[0]["official_source_url"] == OFFICIAL_URL


def test_live_search_called_for_telangana_btech_obc(monkeypatch, live_retriever):
    monkeypatch.setattr("agent.pipeline.recommend_schemes", _eligibility_payload)
    profile = {
        "age": 20,
        "education": "B.Tech",
        "state": "Telangana",
        "category": "OBC",
        "annual_income": 250000,
    }
    result = recommend_for_profile(
        profile, retriever=live_retriever, include_llm_queries=False
    )
    assert live_retriever.calls, "live search must be called at request time"
    assert result["retrieval"]["mode"] == "live_web_search"
    assert result["retrieval"]["provider"] == "tavily"
    assert result["retrieval"]["cached"] is False
    assert result["recommendations"]
    first = result["recommendations"][0]
    assert first["official_source_url"].startswith("https://")
    assert first["source_verification"]["is_official_government_source"] is True
    assert "Telangana" in first["relevance_explanation"]
    json.dumps(result)


def test_female_student_telangana(monkeypatch, live_retriever):
    monkeypatch.setattr("agent.pipeline.recommend_schemes", _eligibility_payload)
    result = recommend_for_profile(
        {
            "age": 19,
            "education": "Undergraduate",
            "state": "Telangana",
            "category": "OBC",
            "gender": "female",
            "annual_income": 180000,
        },
        retriever=live_retriever,
        include_llm_queries=False,
    )
    assert live_retriever.calls
    assert any("women" in query.lower() or "girl" in query.lower() or "telangana" in query.lower() for query in live_retriever.calls)
    assert result["recommendations"]
    json.dumps(result)


def test_general_category_student(monkeypatch, live_retriever):
    monkeypatch.setattr("agent.pipeline.recommend_schemes", _eligibility_payload)
    result = recommend_for_profile(
        {
            "age": 21,
            "education": "B.Tech",
            "state": "Telangana",
            "category": "General",
            "annual_income": 250000,
        },
        retriever=live_retriever,
        include_llm_queries=False,
    )
    statuses = {item["eligibility_status"] for item in result["recommendations"]}
    assert "cannot_confirm" in statuses or result["notice"]
    for item in result["recommendations"]:
        assert "definitely eligible" not in item["relevance_explanation"].lower()
    json.dumps(result)


def test_income_above_common_limits(monkeypatch, live_retriever):
    monkeypatch.setattr("agent.pipeline.recommend_schemes", _eligibility_payload)
    result = recommend_for_profile(
        {
            "age": 28,
            "education": "B.Tech",
            "state": "Telangana",
            "category": "OBC",
            "annual_income": 2500000,
        },
        retriever=live_retriever,
        include_llm_queries=False,
    )
    assert result["recommendations"]
    assert all(
        item["eligibility_status"] == "likely_not_eligible"
        for item in result["recommendations"]
    )
    assert all("2.5 lakh" in item["relevance_explanation"] for item in result["recommendations"])
    json.dumps(result)


def test_search_endpoint_logic(monkeypatch, live_retriever):
    result = search_schemes(
        "scholarships for OBC students",
        retriever=live_retriever,
    )
    assert live_retriever.calls
    assert result["retrieval"]["provider"] == "tavily"
    assert result["schemes"]
    assert all(item.get("official_source_url") for item in result["schemes"])
    json.dumps(result)


def test_live_search_failure_has_no_hardcoded_fallback():
    def fail(query, **kwargs):
        raise LiveSearchError("Tavily unavailable")

    retriever = LiveSchemeRetriever(search_fn=fail, extract_fn=_extract_from_hits)
    with pytest.raises(LiveSearchError):
        recommend_for_profile(
            {"age": 20, "state": "Telangana", "education": "B.Tech", "category": "OBC"},
            retriever=retriever,
            include_llm_queries=False,
        )


def test_api_recommend_json(monkeypatch, api_client, live_retriever):
    monkeypatch.setattr("agent.pipeline.recommend_schemes", _eligibility_payload)
    monkeypatch.setattr("api.main.recommend_for_profile", lambda profile, top_k=8: recommend_for_profile(
        profile, retriever=live_retriever, include_llm_queries=False, top_k=top_k
    ))
    response = api_client.post(
        "/recommend",
        json={
            "age": 20,
            "education": "B.Tech",
            "state": "Telangana",
            "category": "OBC",
            "annual_income": 250000,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "recommendations" in payload
    assert payload["retrieval"]["mode"] == "live_web_search"
    assert live_retriever.calls


def test_api_search_and_health(monkeypatch, api_client, live_retriever):
    monkeypatch.setattr(
        "api.main.search_schemes",
        lambda q, top_k=8: search_schemes(q, retriever=live_retriever, top_k=top_k),
    )
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["stores_schemes"] is False
    response = api_client.get("/schemes/search", params={"q": "scholarships for OBC students"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["schemes"]
    assert payload["retrieval"]["cached"] is False


def test_api_clarify_returns_missing_questions(api_client):
    response = api_client.post(
        "/clarify",
        json={"text": "I am an unemployed OBC woman from Karnataka and need business support."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "profile" in payload
    assert "missing_questions" in payload
    assert any(item["field"] == "age" for item in payload["missing_questions"])
    assert payload["ready_for_recommendation"] is False


def test_api_benefits_journey_preserves_unknown_and_mismatch(monkeypatch, api_client):
    def fake_recommend(profile, top_k=8):
        return {
            "recommendations": [
                {
                    "scheme_name": "Confirmed Student Scholarship",
                    "eligibility_status": "relevant",
                    "relevance_explanation": "Matches student profile.",
                    "official_source_url": OFFICIAL_URL,
                    "source_verification": {"is_official_government_source": True, "domain": "myscheme.gov.in"},
                },
                {
                    "scheme_name": "Income Limited Support",
                    "eligibility_status": "likely_not_eligible",
                    "relevance_explanation": "Income appears above the limit.",
                    "official_source_url": STATE_URL,
                    "source_verification": {"is_official_government_source": True, "domain": "telangana.gov.in"},
                },
                {
                    "scheme_name": "Needs More Information",
                    "eligibility_status": "cannot_confirm",
                    "relevance_explanation": "Source lacks enough information.",
                    "missing_information": ["Income certificate status"],
                    "official_source_url": OFFICIAL_URL,
                    "source_verification": {"is_official_government_source": True, "domain": "myscheme.gov.in"},
                },
            ],
            "retrieval": {"mode": "live_web_search", "cached": False},
        }

    monkeypatch.setattr("api.main.recommend_for_profile", fake_recommend)
    response = api_client.post(
        "/benefits/journey",
        json={
            "age": 20,
            "state": "Telangana",
            "occupation": "Student",
            "category": "OBC",
            "annual_income": 250000,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    states = {step["scheme_name"]: step["eligibility_state"] for step in payload["journey"]}
    assert states["Confirmed Student Scholarship"] == "MATCH"
    assert states["Income Limited Support"] == "MISMATCH"
    assert states["Needs More Information"] == "UNKNOWN"
    assert payload["summary"]["unknown_count"] == 1


def test_api_search_failure_does_not_return_schemes(monkeypatch, api_client):
    def boom(q, top_k=8):
        raise LiveSearchError("provider down")

    monkeypatch.setattr("api.main.search_schemes", boom)
    response = api_client.get("/schemes/search", params={"q": "scholarships"})
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["error"] == "provider_upstream_error"
    assert body["detail"]["provider"] == "tavily"
    assert body["detail"]["fallback_used"] is False
    assert "recommendations" not in body


# ── Production-readiness tests ───────────────────────────────────────────

def test_recommend_runs_pipeline_once_and_returns_journey(monkeypatch, api_client):
    calls = {"n": 0}

    def fake_recommend(profile, top_k=8):
        calls["n"] += 1
        return {
            "recommendations": [
                {
                    "scheme_name": "Scholarship X",
                    "eligibility_status": "relevant",
                    "relevance_explanation": "Matches the student profile.",
                    "official_source_url": OFFICIAL_URL,
                    "source_verification": {
                        "is_official_government_source": True,
                        "domain": "myscheme.gov.in",
                    },
                }
            ],
            "retrieval": {"mode": "live_web_search", "cached": False},
            "notice": None,
        }

    monkeypatch.setattr("api.main.recommend_for_profile", fake_recommend)
    resp = api_client.post(
        "/recommend", json={"age": 20, "state": "Telangana", "category": "OBC"}
    )
    assert resp.status_code == 200
    assert calls["n"] == 1, "/recommend must run the live pipeline exactly once"
    payload = resp.json()
    assert "journey" in payload
    steps = payload["journey"]["journey"]
    assert isinstance(steps, list) and steps[0]["eligibility_state"] == "MATCH"


def test_benefits_journey_with_recommendations_skips_live_search(monkeypatch, api_client):
    def boom(*args, **kwargs):
        raise AssertionError(
            "recommend_for_profile must not run when recommendations are supplied"
        )

    monkeypatch.setattr("api.main.recommend_for_profile", boom)
    resp = api_client.post(
        "/benefits/journey",
        json={
            "age": 20,
            "state": "Telangana",
            "recommendations": [
                {
                    "scheme_name": "A",
                    "eligibility_status": "relevant",
                    "official_source_url": OFFICIAL_URL,
                },
                {
                    "scheme_name": "B",
                    "eligibility_status": "cannot_confirm",
                    "official_source_url": OFFICIAL_URL,
                    "missing_information": ["Income certificate"],
                },
            ],
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    states = {step["scheme_name"]: step["eligibility_state"] for step in payload["journey"]}
    assert states == {"A": "MATCH", "B": "UNKNOWN"}
    assert payload["summary"]["total_options"] == 2


def test_health_reports_config_without_leaking_keys(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stores_schemes"] is False
    cfg = body["config"]
    assert cfg["gemini_api_key_present"] is True
    assert cfg["tavily_api_key_present"] is True
    assert isinstance(cfg["model"], str) and cfg["model"]
    # Actual secret values must never appear in the response.
    assert "test-gemini" not in resp.text
    assert "test-tavily" not in resp.text


def test_clarify_uses_canonical_extraction_and_preserves_unknowns(monkeypatch, api_client):
    monkeypatch.setattr(
        "api.main.extract_profile",
        lambda text, **kwargs: {
            "age": 30,
            "gender": None,
            "state": "Karnataka",
            "education": None,
            "occupation": None,
            "annual_household_income_inr": None,
            "category": None,
            "disability_status": None,
            "farmer_status": None,
        },
    )
    resp = api_client.post("/clarify", json={"text": "I am 30 and live in Karnataka."})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["profile_source"] == "llm"
    profile = payload["profile"]
    assert profile["age"] == 30
    assert profile["state"] == "Karnataka"
    # Unknown values stay None — never coerced to False/empty.
    assert profile["gender"] is None
    assert profile["annual_household_income_inr"] is None
    assert profile["category"] is None
    assert payload["ready_for_recommendation"] is False
    fields = {question["field"] for question in payload["missing_questions"]}
    assert "annual_household_income_inr" in fields


def test_clarify_does_not_overwrite_provided_fields_with_none(monkeypatch, api_client):
    monkeypatch.setattr(
        "api.main.extract_profile",
        lambda text, **kwargs: {
            "age": None, "gender": None, "state": None, "education": None,
            "occupation": None, "annual_household_income_inr": None,
            "category": None, "disability_status": None, "farmer_status": None,
        },
    )
    resp = api_client.post("/clarify", json={"text": "something", "age": 42, "state": "Goa"})
    assert resp.status_code == 200
    profile = resp.json()["profile"]
    assert profile["age"] == 42
    assert profile["state"] == "Goa"


def test_ungrounded_non_government_url_is_rejected():
    retriever = LiveSchemeRetriever(
        search_fn=lambda query, **kwargs: [_official_hit()],
        extract_fn=lambda hits, profile, **kwargs: [
            {"scheme_name": "Sketchy Blog Scheme", "official_source_url": "https://random-blog.com/x"},
            {"scheme_name": "Real Official Scheme", "official_source_url": OFFICIAL_URL},
        ],
    )
    schemes = retriever.retrieve_schemes({"state": "Telangana"}, include_llm_queries=False)
    names = [item["scheme_name"] for item in schemes]
    assert "Sketchy Blog Scheme" not in names
    assert names == ["Real Official Scheme"]
    assert schemes[0]["source_verification"]["is_official_government_source"] is True
    assert not is_official_government_url("https://random-blog.com/x")


def test_model_config_is_single_source_of_truth(monkeypatch):
    from agent import model_config

    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-a, gemini-b,gemini-a")
    assert model_config.get_model_name() == "gemini-test-primary"
    # De-duplicated, primary first.
    assert model_config.ordered_models() == ["gemini-test-primary", "gemini-a", "gemini-b"]


def test_generate_with_fallback_raises_when_all_models_fail():
    from agent import model_config

    class _StubModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("model unavailable")

    class _StubClient:
        models = _StubModels()

    with pytest.raises(RuntimeError):
        model_config.generate_with_fallback(_StubClient(), "x", config=None, purpose="test")


def test_rate_limiter_blocks_after_limit(monkeypatch):
    import api.main as api_main

    monkeypatch.setattr(api_main, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(api_main, "RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(api_main, "RATE_LIMIT_WINDOW_SECONDS", 60.0)
    api_main._rate_buckets.clear()

    class _FakeRequest:
        headers: dict = {}

        class client:
            host = "203.0.113.9"

    request = _FakeRequest()
    api_main.rate_limit(request)
    api_main.rate_limit(request)
    with pytest.raises(HTTPException) as excinfo:
        api_main.rate_limit(request)
    assert excinfo.value.status_code == 429
    api_main._rate_buckets.clear()
