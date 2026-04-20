"""test_api_lookup.py — Unit tests for api_lookup.py."""
import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

import api_lookup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    """Return a mock httpx.Response with the given status code and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    # raise_for_status should raise on 4xx/5xx
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Test 1: Valid Clerk "errors" endpoint returns a string containing response data
# ---------------------------------------------------------------------------

def test_clerk_errors_returns_string_with_data(monkeypatch):
    """Happy path: Clerk errors endpoint returns formatted string with response data."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("CLERK_DOMAIN", "test.clerk.dev")

    mock_resp = _mock_response(200, {"errors": [{"code": "E001", "message": "test error"}]})

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = api_lookup.fetch("clerk", "errors")

    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain the response data in some form
    assert "E001" in result or "errors" in result
    mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: Valid Anthropic "models" endpoint returns a string containing response data
# ---------------------------------------------------------------------------

def test_anthropic_models_returns_string_with_data(monkeypatch):
    """Happy path: Anthropic models endpoint returns formatted string with response data."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")

    mock_resp = _mock_response(200, {"data": [{"id": "claude-sonnet-4-6", "type": "model"}]})

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = api_lookup.fetch("anthropic", "models")

    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain the response data in some form
    assert "claude-sonnet-4-6" in result or "models" in result
    mock_get.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Clerk "jwks" endpoint substitutes {clerk_domain} from CLERK_DOMAIN env var
# ---------------------------------------------------------------------------

def test_clerk_jwks_substitutes_clerk_domain(monkeypatch):
    """JWKS URL has {clerk_domain} placeholder replaced with CLERK_DOMAIN env var."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("CLERK_DOMAIN", "myapp.clerk.accounts.dev")

    mock_resp = _mock_response(200, {"keys": [{"kid": "abc", "kty": "RSA"}]})

    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = api_lookup.fetch("clerk", "jwks")

    assert isinstance(result, str)
    # The URL used should contain the actual domain, not the placeholder
    call_url = mock_get.call_args[0][0]
    assert "myapp.clerk.accounts.dev" in call_url
    assert "{clerk_domain}" not in call_url


# ---------------------------------------------------------------------------
# Test 4: Endpoint key not in allowlist returns error string, no HTTP call made
# ---------------------------------------------------------------------------

def test_unknown_endpoint_returns_error_no_http_call(monkeypatch):
    """Endpoint not in allowlist returns error string without making any HTTP call."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc123")

    with patch("httpx.get") as mock_get:
        result = api_lookup.fetch("clerk", "not_a_real_endpoint")

    assert isinstance(result, str)
    assert "error" in result.lower() or "unknown" in result.lower() or "not" in result.lower()
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: HTTP 4xx response returns error string
# ---------------------------------------------------------------------------

def test_http_4xx_returns_error_string(monkeypatch):
    """HTTP 4xx from the API returns an error string without raising."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("CLERK_DOMAIN", "test.clerk.dev")

    mock_resp = _mock_response(403, {"error": "Forbidden"})

    with patch("httpx.get", return_value=mock_resp):
        result = api_lookup.fetch("clerk", "errors")

    assert isinstance(result, str)
    assert "error" in result.lower() or "403" in result or "forbidden" in result.lower()


# ---------------------------------------------------------------------------
# Test 6: Network timeout returns error string
# ---------------------------------------------------------------------------

def test_network_timeout_returns_error_string(monkeypatch):
    """httpx.TimeoutException returns error string without raising."""
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_abc123")
    monkeypatch.setenv("CLERK_DOMAIN", "test.clerk.dev")

    with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
        result = api_lookup.fetch("clerk", "errors")

    assert isinstance(result, str)
    assert "timeout" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# Test 7: Missing CLERK_SECRET_KEY for Clerk call returns error string (no HTTP call)
# ---------------------------------------------------------------------------

def test_missing_clerk_secret_key_returns_error_no_http_call(monkeypatch):
    """Missing CLERK_SECRET_KEY returns error string without making an HTTP call."""
    # Ensure the env var is absent
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.setenv("CLERK_DOMAIN", "test.clerk.dev")

    with patch("httpx.get") as mock_get:
        result = api_lookup.fetch("clerk", "errors")

    assert isinstance(result, str)
    assert "error" in result.lower() or "missing" in result.lower() or "key" in result.lower()
    mock_get.assert_not_called()
