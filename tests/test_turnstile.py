"""test_turnstile.py — Guest tokens are minted only after Cloudflare Turnstile accepts the request."""

import logging
import socket
import urllib.request
from unittest.mock import patch

import pytest

from app import check_startup_config

TEST_SECRET = "test-turnstile-secret-placeholder"


@pytest.fixture
def turnstile_on(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "TURNSTILE_SECRET_KEY", TEST_SECRET)
    return app_module


def _mint(client, body=None):
    return client.post("/guest-token", json=body if body is not None else {"turnstile_token": "tok-abc"})


# ── Verification outcomes on /guest-token ─────────────────────────────────────

def test_turnstile_success_issues_guest_token(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", return_value={"success": True, "action": "guest_token"}) as post:
        resp = _mint(client)
    assert resp.status_code == 200
    assert "token" in resp.get_json()
    assert post.call_args.args[0]["response"] == "tok-abc"


def test_turnstile_rejection_returns_403_and_no_token(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", return_value={"success": False, "error-codes": ["invalid-input-response"]}):
        resp = _mint(client)
    assert resp.status_code == 403
    assert "token" not in resp.get_json()


def test_turnstile_timeout_fails_closed_with_503(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", side_effect=TimeoutError("timed out")):
        resp = _mint(client)
    assert resp.status_code == 503
    assert "token" not in resp.get_json()


def test_turnstile_network_timeout_from_urlopen_fails_closed(client, turnstile_on, monkeypatch):
    """Exercises the real request path with urlopen raising a socket timeout."""
    def boom(*args, **kwargs):
        raise socket.timeout("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    resp = _mint(client)
    assert resp.status_code == 503


def test_turnstile_non_json_response_fails_closed(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", side_effect=ValueError("not json")):
        resp = _mint(client)
    assert resp.status_code == 503


def test_missing_turnstile_token_is_refused_without_calling_cloudflare(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile") as post:
        resp = _mint(client, body={})
        resp_bad_type = _mint(client, body={"turnstile_token": 42})
    assert resp.status_code == 403
    assert resp_bad_type.status_code == 403
    post.assert_not_called()


def test_oversized_turnstile_token_is_refused(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile") as post:
        resp = _mint(client, body={"turnstile_token": "x" * 4097})
    assert resp.status_code == 403
    post.assert_not_called()


# ── verify_turnstile request shape ────────────────────────────────────────────

def test_verify_sends_secret_response_and_remoteip(turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", return_value={"success": True, "action": "guest_token"}) as post:
        assert turnstile_on.verify_turnstile("tok-xyz", "203.0.113.7") is True
    assert post.call_args.args[0] == {"secret": TEST_SECRET, "response": "tok-xyz", "remoteip": "203.0.113.7"}


def test_verify_treats_non_true_success_as_rejected(turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", return_value={"success": "yes"}):
        assert turnstile_on.verify_turnstile("tok", "203.0.113.7") is False


def test_wrong_action_returns_403_and_no_token(client, turnstile_on):
    ok_but_other_widget = {"success": True, "action": "contact_form", "hostname": "example.test"}
    with patch.object(turnstile_on, "_post_turnstile", return_value=ok_but_other_widget):
        resp = _mint(client)
    assert resp.status_code == 403
    assert "token" not in resp.get_json()


def test_missing_action_returns_403(client, turnstile_on):
    with patch.object(turnstile_on, "_post_turnstile", return_value={"success": True}):
        resp = _mint(client)
    assert resp.status_code == 403


def test_wrong_hostname_returns_403_when_allow_list_set(client, turnstile_on, monkeypatch):
    monkeypatch.setattr(turnstile_on, "TURNSTILE_EXPECTED_HOSTNAMES", {"app.example.test"})
    ok_on_other_host = {"success": True, "action": "guest_token", "hostname": "evil.example.test"}
    with patch.object(turnstile_on, "_post_turnstile", return_value=ok_on_other_host):
        resp = _mint(client)
    assert resp.status_code == 403
    assert "token" not in resp.get_json()


def test_matching_hostname_issues_token_when_allow_list_set(client, turnstile_on, monkeypatch):
    monkeypatch.setattr(turnstile_on, "TURNSTILE_EXPECTED_HOSTNAMES", {"app.example.test"})
    ok = {"success": True, "action": "guest_token", "hostname": "app.example.test"}
    with patch.object(turnstile_on, "_post_turnstile", return_value=ok):
        resp = _mint(client)
    assert resp.status_code == 200


def test_hostname_is_not_checked_when_allow_list_unset(client, turnstile_on, monkeypatch):
    monkeypatch.setattr(turnstile_on, "TURNSTILE_EXPECTED_HOSTNAMES", set())
    ok = {"success": True, "action": "guest_token", "hostname": "anything.example.test"}
    with patch.object(turnstile_on, "_post_turnstile", return_value=ok):
        resp = _mint(client)
    assert resp.status_code == 200


# ── Off production ────────────────────────────────────────────────────────────

def test_missing_secret_off_production_skips_verification_with_warning(client, monkeypatch, caplog):
    import app as app_module
    monkeypatch.setattr(app_module, "TURNSTILE_SECRET_KEY", "")
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    with patch.object(app_module, "_post_turnstile") as post, \
         caplog.at_level(logging.WARNING, logger="app"):
        resp = _mint(client, body={})
    assert resp.status_code == 200
    post.assert_not_called()
    assert any("skipping bot verification" in r.message for r in caplog.records)


def test_missing_secret_in_production_at_runtime_fails_closed(client, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "TURNSTILE_SECRET_KEY", "")
    monkeypatch.setenv("VERCEL_ENV", "production")
    resp = _mint(client)
    assert resp.status_code == 503
    assert "token" not in resp.get_json()


# ── Startup ───────────────────────────────────────────────────────────────────

def test_production_missing_turnstile_key_is_a_startup_error():
    env = {"VERCEL": "1", "VERCEL_ENV": "production", "REDIS_URL": "redis://x", "GUEST_JWT_SECRET": "x" * 32}
    with pytest.raises(RuntimeError, match="TURNSTILE_SECRET_KEY is required on Vercel production"):
        check_startup_config(env)
