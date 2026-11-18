"""test_auth.py — Tests for the require_auth decorator on /ask."""

import time
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import app as app_module


def test_missing_authorization_header_returns_401(client):
    resp = client.post("/ask", json={"question": "test"})
    assert resp.status_code == 401
    assert b"Unauthorized" in resp.data


def test_malformed_token_returns_401(client, mock_jwks):
    resp = client.post(
        "/ask",
        json={"question": "test"},
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert resp.status_code == 401


def test_expired_token_returns_401(client, mock_jwks, expired_token):
    resp = client.post(
        "/ask",
        json={"question": "test"},
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert b"expired" in resp.data.lower()


def test_jwks_fetch_failure_returns_503(client, valid_token):
    """When _fetch_jwks raises URLError, the route should return 503."""
    import app as app_module

    def _raise_url_error():
        raise urllib.error.URLError("connection refused")

    with patch.object(app_module, "_fetch_jwks", side_effect=_raise_url_error):
        resp = client.post(
            "/ask",
            json={"question": "test"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 503


def test_valid_token_passes_auth_to_route(client, mock_jwks, valid_token):
    """A valid token should reach the route. 415 = content-type rejected by route, not auth."""
    resp = client.post(
        "/ask",
        content_type="text/plain",
        data="not json",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp.status_code == 415


def _fake_jwks_response(body: bytes):
    """Stand-in for urlopen() that returns a 200 with the given body."""
    response = MagicMock()
    response.read.return_value = body
    context = MagicMock()
    context.__enter__.return_value = response
    return MagicMock(return_value=context)


def test_non_json_jwks_200_keeps_cached_keys(jwks_state, fake_jwks, valid_token):
    """A 200 whose body is not JSON must not replace the good cache."""
    _set_jwks_state(jwks_state, fake_jwks, cached_age=7200, attempt_age=120)
    fake_urlopen = _fake_jwks_response(b"<html>maintenance</html>")
    with patch.object(app_module.urllib.request, "urlopen", fake_urlopen):
        payload = app_module.verify_clerk_token(valid_token)
    assert payload["sub"] == "user_test123"
    assert fake_urlopen.call_count == 1


def test_jwks_200_without_keys_list_keeps_cached_keys(jwks_state, fake_jwks, valid_token):
    """A 200 JSON body without a keys list must not replace the good cache."""
    _set_jwks_state(jwks_state, fake_jwks, cached_age=7200, attempt_age=120)
    fake_urlopen = _fake_jwks_response(b'{"error": "unexpected"}')
    with patch.object(app_module.urllib.request, "urlopen", fake_urlopen):
        payload = app_module.verify_clerk_token(valid_token)
    assert payload["sub"] == "user_test123"
    assert fake_urlopen.call_count == 1


# ── JWKS cache, unknown-kid refetch, and upstream failures ────────────────────

@pytest.fixture
def jwks_state(monkeypatch):
    """Start each JWKS test with an empty cache; monkeypatch restores the globals."""
    monkeypatch.setattr(app_module, "_jwks_cache", None)
    monkeypatch.setattr(app_module, "_jwks_cached_at", 0.0)
    monkeypatch.setattr(app_module, "_jwks_last_attempt_at", 0.0)
    return monkeypatch


def _set_jwks_state(monkeypatch, cache, *, cached_age, attempt_age):
    """Place the cache `cached_age` seconds old, last attempted `attempt_age` seconds ago."""
    now = time.time()
    monkeypatch.setattr(app_module, "_jwks_cache", cache)
    monkeypatch.setattr(app_module, "_jwks_cached_at", now - cached_age)
    monkeypatch.setattr(app_module, "_jwks_last_attempt_at", now - attempt_age)


def test_unknown_kid_refetches_once_and_accepts_rotated_key(jwks_state, fake_jwks, valid_token):
    _set_jwks_state(jwks_state, {"keys": []}, cached_age=10, attempt_age=120)
    download = MagicMock(return_value=fake_jwks)
    with patch.object(app_module, "_download_jwks", download):
        payload = app_module.verify_clerk_token(valid_token)
    assert payload["sub"] == "user_test123"
    assert download.call_count == 1


def test_unknown_kid_refetch_is_rate_limited(jwks_state, valid_token):
    """A refetch attempted within the last 60 s is skipped, so bogus kids cannot hammer Clerk."""
    _set_jwks_state(jwks_state, {"keys": []}, cached_age=10, attempt_age=10)
    download = MagicMock()
    with patch.object(app_module, "_download_jwks", download), pytest.raises(ValueError):
        app_module.verify_clerk_token(valid_token)
    assert download.call_count == 0


def test_unknown_kid_still_rejected_after_refetch(jwks_state, valid_token):
    _set_jwks_state(jwks_state, {"keys": []}, cached_age=10, attempt_age=120)
    download = MagicMock(return_value={"keys": []})
    with patch.object(app_module, "_download_jwks", download), pytest.raises(ValueError, match="No matching JWK"):
        app_module.verify_clerk_token(valid_token)
    assert download.call_count == 1


def test_failed_refresh_serves_stale_cache(jwks_state, fake_jwks, valid_token):
    """An expired cache is still used when Clerk cannot be reached."""
    _set_jwks_state(jwks_state, fake_jwks, cached_age=7200, attempt_age=120)
    download = MagicMock(side_effect=urllib.error.URLError("connection refused"))
    with patch.object(app_module, "_download_jwks", download):
        payload = app_module.verify_clerk_token(valid_token)
    assert payload["sub"] == "user_test123"
    assert download.call_count == 1


@pytest.mark.parametrize(
    "error",
    [urllib.error.URLError("connection refused"), TimeoutError("timed out"), OSError("network down")],
)
def test_jwks_upstream_failure_without_cache_returns_503(client, jwks_state, valid_token, error):
    """Network-level failures are upstream outages (503), never auth failures (401)."""
    download = MagicMock(side_effect=error)
    with patch.object(app_module, "_download_jwks", download):
        resp = client.post(
            "/ask",
            json={"question": "test"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 503
