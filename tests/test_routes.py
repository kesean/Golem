"""test_routes.py — Integration tests for the /ask route."""

from unittest.mock import MagicMock, patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_message(text):
    """Return a mock object matching the shape of anthropic.types.Message."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


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
    with patch("app.client.messages.create", return_value=_fake_message(xml)):
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


def test_history_is_forwarded_to_anthropic(client, mock_jwks, valid_token):
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    xml = "<product_tag>Other</product_tag><summary>ok</summary>"
    with patch("app.client.messages.create", return_value=_fake_message(xml)) as mock_create:
        client.post(
            "/ask",
            json={"question": "Follow-up?", "history": history},
            headers=_auth_headers(valid_token),
        )
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "Previous question"}
    assert messages[-1] == {"role": "user", "content": "Follow-up?"}
