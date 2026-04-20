"""test_routes.py — Integration tests for the /ask route."""

from unittest.mock import patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_chat_result(text, input_tokens=10, output_tokens=20, latency_ms=42):
    """Return a dict matching the shape of chat.run()'s return value."""
    return {
        "response": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
    }


# ── Input validation ──────────────────────────────────────────────────────────

def test_non_json_content_type_returns_415(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        content_type="text/plain",
        data="hello",
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 415


def test_missing_question_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": ""},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


def test_question_over_2000_chars_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": "x" * 2001},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400
    assert b"2000" in resp.data


def test_invalid_history_format_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": "test?", "history": "not-a-list"},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_request_returns_json_response(client, mock_jwks, valid_token):
    xml = "<product_tag>Authentication</product_tag><summary>Test</summary>"
    with patch("app.chat_run", return_value=_fake_chat_result(xml)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert "response" in data
    assert "Authentication" in data["response"]
    assert "Test" in data["response"]


def test_history_is_forwarded_to_chat_run(client, mock_jwks, valid_token):
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    xml = "<product_tag>Other</product_tag><summary>ok</summary>"
    with patch("app.chat_run", return_value=_fake_chat_result(xml)) as mock_run:
        client.post(
            "/ask",
            json={"question": "Follow-up?", "history": history},
            headers=_auth_headers(valid_token),
        )
    _, call_history = mock_run.call_args.args
    assert call_history[0] == {"role": "user", "content": "Previous question"}
    assert call_history[1] == {"role": "assistant", "content": "Previous answer"}
    assert len(call_history) == 2


def test_response_includes_token_usage_and_latency(client, mock_jwks, valid_token):
    xml = "<product_tag>Authentication</product_tag><summary>Test</summary>"
    with patch("app.chat_run", return_value=_fake_chat_result(xml, input_tokens=50, output_tokens=100, latency_ms=77)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["input_tokens"] == 50
    assert data["output_tokens"] == 100
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0


def test_chat_run_runtime_error_returns_502(client, mock_jwks, valid_token):
    """RuntimeError from chat.run() produces a 502 with the error message."""
    with patch("app.chat_run", side_effect=RuntimeError("No response from model")):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 502
    data = resp.get_json()
    assert data["error"] == "No response from model"
