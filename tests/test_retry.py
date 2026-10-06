"""Retry-helper tests: transient vs permanent, backoff, exhaustive failures."""

from __future__ import annotations

import pytest

from agent import retry


def test_transient_then_success(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("HTTP 503 Service Unavailable")
        return "ok"

    assert retry.with_retries(flaky, provider="tavily", operation="search") == "ok"
    assert calls["n"] == 3


def test_all_retries_fail(monkeypatch):
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def always():
        raise TimeoutError("timed out")

    with pytest.raises(TimeoutError):
        retry.with_retries(always, provider="gemini", operation="eligibility", max_retries=2)


def test_auth_error_not_retried(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def auth():
        calls["n"] += 1
        raise Exception("401 Unauthorized: invalid api key")

    with pytest.raises(Exception):
        retry.with_retries(auth, provider="gemini", operation="scheme-extraction")
    assert calls["n"] == 1


def test_timeout_retried(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def t():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("gemini timed out")
        return "ok"

    assert retry.with_retries(t, provider="gemini", operation="query-generation") == "ok"
    assert calls["n"] == 2


def test_429_retried(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def q():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("429 RESOURCE_EXHAUSTED")
        return "ok"

    assert retry.with_retries(q, provider="gemini", operation="eligibility") == "ok"
    assert calls["n"] == 2
