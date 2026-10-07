import pytest
from rag.live_retriever import check_state_relevance, check_need_relevance, SearchHit, _validate_scheme_relevance, RetrievalDiagnostics, _annotate_hit

def test_state_mismatch():
    hit = SearchHit(title="Kerala Scheme", url="https://kerala.gov.in/scheme", content="Kerala only.")
    _annotate_hit(hit, "Telangana", "")
    ok, reason = check_state_relevance(hit, "Telangana")
    assert not ok
    assert "wrong_state:kerala" in reason

def test_central_scheme_allowed():
    hit = SearchHit(title="PM Kisan", url="https://pmkisan.gov.in", content="Central scheme for farmers.")
    _annotate_hit(hit, "Telangana", "")
    ok, reason = check_state_relevance(hit, "Telangana")
    assert ok
    assert reason == "central_scheme"

def test_need_mismatch():
    hit = SearchHit(title="Education Scholarship", url="https://ap.gov.in", content="For students only.")
    _annotate_hit(hit, "", "Agriculture")
    ok, reason = check_need_relevance(hit, "Agriculture")
    assert not ok
    assert "wrong_need" in reason

def test_safe_no_match():
    diag = RetrievalDiagnostics()
    schemes = [{"scheme_name": "Kerala Scheme", "official_source_url": "https://kerala.gov.in", "description": "Kerala only"}]
    res = _validate_scheme_relevance(schemes, "Telangana", "", diag)
    assert len(res) == 0
