"""test_routes.py — Integration tests for the /ask/stream route."""

from unittest.mock import patch


class _FakeStreamCtx:
    """Minimal context manager that mimics anthropic MessageStream."""

    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Input validation ──────────────────────────────────────────────────────────

def test_non_json_content_type_returns_415(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask/stream",
        content_type="text/plain",
        data="hello",
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 415


def test_missing_question_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask/stream",
        json={"question": ""},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


def test_question_over_2000_chars_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask/stream",
        json={"question": "x" * 2001},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400
    assert b"2000" in resp.data


def test_invalid_history_format_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask/stream",
        json={"question": "test?", "history": "not-a-list"},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_request_streams_text_response(client, mock_jwks, valid_token):
    fake_chunks = ["<product_tag>Authentication</product_tag>", "<summary>Test</summary>"]
    with patch("app.client.messages.stream", return_value=_FakeStreamCtx(fake_chunks)):
        resp = client.post(
            "/ask/stream",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/plain")
    assert b"Authentication" in resp.data
    assert b"Test" in resp.data


def test_history_is_forwarded_to_anthropic(client, mock_jwks, valid_token):
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    with patch("app.client.messages.stream", return_value=_FakeStreamCtx(["ok"])) as mock_stream:
        client.post(
            "/ask/stream",
            json={"question": "Follow-up?", "history": history},
            headers=_auth_headers(valid_token),
        )
    messages = mock_stream.call_args.kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "Previous question"}
    assert messages[-1] == {"role": "user", "content": "Follow-up?"}
