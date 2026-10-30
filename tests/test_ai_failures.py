"""Optional Gemini integration: every failure path ends in a friendly message, never a crash,
and nothing secret or personal reaches the logs. The network is faked; no key is needed."""

from __future__ import annotations

import logging

import pytest
import requests

from src import ai


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("SPENDLY_ENABLE_AI", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real-123")


class _Response:
    def __init__(self, status: int, body=None, bad_json: bool = False):
        self.status_code = status
        self._body = body
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._body


def _reply(text: str) -> _Response:
    return _Response(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


@pytest.mark.parametrize("error, message", [
    (requests.Timeout(), "Could not reach the Gemini API"),
    (requests.ConnectionError(), "Could not reach the Gemini API"),
])
def test_network_failures_give_a_friendly_error(enabled, monkeypatch, error, message):
    def boom(*args, **kwargs):
        raise error
    monkeypatch.setattr(ai.requests, "post", boom)
    with pytest.raises(ai.AIError, match=message):
        ai.suggest_categories(["Green Leaf Salon"])


@pytest.mark.parametrize("status, message", [
    (429, "rate limit"),
    (401, "rejected the API key"),
    (403, "rejected the API key"),
    (500, r"HTTP 500"),
])
def test_http_errors_give_a_friendly_error(enabled, monkeypatch, status, message):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: _Response(status, {}))
    with pytest.raises(ai.AIError, match=message):
        ai.suggest_categories(["Green Leaf Salon"])


@pytest.mark.parametrize("response", [
    _Response(200, bad_json=True),                 # body isn't JSON
    _Response(200, {"candidates": []}),            # no answer in it
])
def test_malformed_responses_give_a_friendly_error(enabled, monkeypatch, response):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: response)
    with pytest.raises(ai.AIError, match="unexpected response"):
        ai.suggest_categories(["Green Leaf Salon"])


def test_an_answer_that_is_not_json_changes_nothing(enabled, monkeypatch):
    monkeypatch.setattr(ai.requests, "post", lambda *a, **k: _reply("Shopping, I think"))
    with pytest.raises(ai.AIError, match="not valid JSON"):
        ai.suggest_categories(["Green Leaf Salon"])
    # The summary feature falls back silently to the rule-based text.
    assert ai.rephrase_insights(["You spent ₹1,000 in May 2026."]) is None


def test_only_sanitized_labels_are_sent_and_the_key_stays_in_a_header(enabled, monkeypatch, caplog):
    sent = {}

    def capture(url, headers=None, json=None, timeout=None):
        sent.update(url=url, headers=headers, body=json, timeout=timeout)
        return _reply('{"Green Leaf Salon": "Shopping"}')

    monkeypatch.setattr(ai.requests, "post", capture)
    caplog.set_level(logging.DEBUG)
    ai.suggest_categories(["UPI/412345678901/greenleaf@okaxis/Green Leaf Salon 9876543210"])

    prompt = sent["body"]["contents"][0]["parts"][0]["text"]
    for secret in ("412345678901", "okaxis", "9876543210"):
        assert secret not in prompt
    assert "test-key-not-real-123" not in sent["url"]          # key is a header, not in the URL
    assert sent["headers"]["x-goog-api-key"] == "test-key-not-real-123"
    assert sent["timeout"] == 20                               # requests never hang
    assert "test-key-not-real-123" not in caplog.text
    assert "Green Leaf" not in caplog.text                     # logs carry counts, not merchant names


def test_nothing_is_sent_when_ai_is_off(monkeypatch):
    monkeypatch.delenv("SPENDLY_ENABLE_AI", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real-123")

    def must_not_call(*a, **k):
        raise AssertionError("no request may be made when AI is off")
    monkeypatch.setattr(ai.requests, "post", must_not_call)
    with pytest.raises(ai.AIError, match="not enabled"):
        ai.suggest_categories(["Green Leaf Salon"])
