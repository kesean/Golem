"""test_stats_counter.py — The answered-question counter is written by the backend, only after a successful answer."""

import logging
import socket
import urllib.request
from unittest.mock import MagicMock, patch

import pytest


def _fake_chat_result():
    text = "<summary>ok</summary>"
    return [
        {"type": "delta", "text": text},
        {"type": "done", "response": text, "input_tokens": 1, "output_tokens": 1, "latency_ms": 1, "chunks": []},
    ]


@pytest.fixture
def convex_configured(monkeypatch):
    monkeypatch.setenv("CONVEX_SITE_URL", "https://example-deployment.convex.site/")
    monkeypatch.setenv("STATS_INCREMENT_SECRET", "test-stats-secret")


def _ask(client, token):
    resp = client.post("/ask", json={"question": "q"}, headers={"Authorization": f"Bearer {token}"})
    resp.get_data()
    return resp


def test_successful_answer_posts_one_increment_with_bearer_secret(client, mock_jwks, valid_token, convex_configured):
    fake_response = MagicMock()
    fake_response.__enter__.return_value.read.return_value = b'{"ok": true}'
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
        resp = _ask(client, valid_token)
    assert resp.status_code == 200
    urlopen.assert_called_once()
    req = urlopen.call_args.args[0]
    assert isinstance(req, urllib.request.Request)
    assert req.full_url == "https://example-deployment.convex.site/stats/increment"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer test-stats-secret"
    assert urlopen.call_args.kwargs["timeout"] == 3


def test_failed_answer_does_not_touch_the_counter(client, mock_jwks, valid_token, convex_configured):
    with patch("app.chat_run", side_effect=RuntimeError("upstream down")), \
         patch("urllib.request.urlopen") as urlopen:
        resp = _ask(client, valid_token)
    assert resp.status_code == 200  # SSE stream opened; the failure arrives as an error event
    assert b'"type": "error"' in resp.data
    urlopen.assert_not_called()


def test_counter_failure_never_reaches_the_user(client, mock_jwks, valid_token, convex_configured, caplog):
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")), \
         caplog.at_level(logging.WARNING, logger="app"):
        resp = _ask(client, valid_token)
    assert resp.status_code == 200
    assert b'"type": "done"' in resp.data
    assert any("counter update failed" in r.message for r in caplog.records)


def test_missing_convex_config_skips_the_call_with_a_warning(client, mock_jwks, valid_token, monkeypatch, caplog):
    monkeypatch.delenv("CONVEX_SITE_URL", raising=False)
    monkeypatch.delenv("STATS_INCREMENT_SECRET", raising=False)
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         patch("urllib.request.urlopen") as urlopen, \
         caplog.at_level(logging.WARNING, logger="app"):
        resp = _ask(client, valid_token)
    assert resp.status_code == 200
    urlopen.assert_not_called()
    assert any("not updated" in r.message for r in caplog.records)
