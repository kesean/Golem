"""test_auth.py — Tests for the require_auth decorator on /ask/stream."""

import urllib.error
from unittest.mock import patch


def test_missing_authorization_header_returns_401(client):
    resp = client.post("/ask/stream", json={"question": "test"})
    assert resp.status_code == 401
    assert b"Unauthorized" in resp.data


def test_malformed_token_returns_401(client, mock_jwks):
    resp = client.post(
        "/ask/stream",
        json={"question": "test"},
        headers={"Authorization": "Bearer not.a.jwt"},
    )
    assert resp.status_code == 401


def test_expired_token_returns_401(client, mock_jwks, expired_token):
    resp = client.post(
        "/ask/stream",
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
            "/ask/stream",
            json={"question": "test"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert resp.status_code == 503


def test_valid_token_passes_auth_to_route(client, mock_jwks, valid_token):
    """A valid token should reach the route. 415 = content-type rejected by route, not auth."""
    resp = client.post(
        "/ask/stream",
        content_type="text/plain",
        data="not json",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp.status_code == 415
