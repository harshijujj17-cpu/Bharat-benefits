"""Provider-abstraction tests: mocked providers, zero API quota."""

from __future__ import annotations

import json

import pytest

from agent import llm_client


def test_default_provider_is_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert llm_client.get_provider() == "gemini"


def test_provider_env_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    assert llm_client.get_provider() == "openai_compatible"


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "some-free-model")
    monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)
    assert llm_client.get_primary_model() == "some-free-model"
    assert "some-free-model" in llm_client.ordered_models()


def test_generate_uses_configured_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    called = {}

    def fake_openai(prompt, *, system_instruction, response_schema, temperature, model_name, purpose):
        called.update(provider="openai_compatible", model=model_name, purpose=purpose)
        return llm_client.LLMResponse(json.dumps({"queries": ["q1"]}))

    monkeypatch.setattr(llm_client, "_openai_compatible_generate", fake_openai)
    resp = llm_client.generate("hello", purpose="query-generation")
    assert json.loads(resp.text) == {"queries": ["q1"]}
    assert called["provider"] == "openai_compatible"
    assert called["purpose"] == "query-generation"


def test_generate_falls_back_to_second_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "primary-model")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "primary-model,backup-model")
    attempts = []

    def fake_gemini(prompt, *, system_instruction, response_schema, temperature, model_name, purpose):
        attempts.append(model_name)
        if model_name == "primary-model":
            raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")
        return llm_client.LLMResponse('{"ok": true}')

    monkeypatch.setattr(llm_client, "_gemini_generate", fake_gemini)
    resp = llm_client.generate("hi", purpose="eligibility")
    assert attempts == ["primary-model", "backup-model"]
    assert json.loads(resp.text)["ok"] is True


def test_generate_raises_last_error_when_all_fail(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "m1")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "m2")

    def fake_gemini(prompt, *, system_instruction, response_schema, temperature, model_name, purpose):
        raise TimeoutError("gemini timed out")

    monkeypatch.setattr(llm_client, "_gemini_generate", fake_gemini)
    with pytest.raises(TimeoutError):
        llm_client.generate("hi", purpose="scheme-extraction")


def test_scheme_extraction_and_eligibility_use_llm_client(monkeypatch):
    """The four call sites route through llm_client when no explicit client is passed."""
    from agent import profile_extractor, recommendation, scheme_extractor, query_builder
    from rag.live_retriever import SearchHit

    seen = []

    def fake_generate(prompt, *, system_instruction=None, response_schema=None,
                      temperature=0.0, purpose="llm", model_name=None):
        seen.append(purpose)
        if purpose == "scheme-extraction":
            return llm_client.LLMResponse(json.dumps({"schemes": []}))
        if purpose == "eligibility":
            return llm_client.LLMResponse(json.dumps({"recommendations": [{"scheme_name": "S", "relevance_explanation": "ok", "missing_information": [], "eligibility_status": "relevant"}]}))
        if purpose == "profile-extraction":
            return llm_client.LLMResponse(json.dumps({}))
        return llm_client.LLMResponse(json.dumps({"queries": []}))

    monkeypatch.setattr(llm_client, "generate", fake_generate)

    monkeypatch.setattr("agent.query_builder.llm_client", llm_client, raising=False)
    query_builder.build_search_queries({"state": "Telangana"}, include_llm=True)
    scheme_extractor.extract_schemes_from_hits([SearchHit(title="t", url="https://myscheme.gov.in/x", content="c")])
    profile_extractor.extract_profile("I am a farmer in Gujarat")
    recommendation.recommend_schemes({"age": 20}, [{"scheme_name": "S", "official_source_url": "https://myscheme.gov.in/x"}])

    assert "query-generation" in seen
    assert "scheme-extraction" in seen
    assert "profile-extraction" in seen
    assert "eligibility" in seen
