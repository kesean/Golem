"""test_routes.py — Integration tests for the /ask route."""

import json
from unittest.mock import patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_chat_events(text, input_tokens=10, output_tokens=20, latency_ms=42):
    """Return events matching the shape chat.stream_run() yields.

    A plain list (not a generator) so the same patched return_value can be
    iterated once per request across multiple requests in one test.
    """
    return [
        {"type": "delta", "text": text},
        {
            "type": "done",
            "response": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
        },
    ]


def _parse_sse(data: bytes) -> list:
    """Parse a text/event-stream body into a list of decoded JSON events."""
    events = []
    for line in data.decode().split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


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

def test_valid_request_streams_sse_response(client, mock_jwks, valid_token):
    xml = "<product_tag>Authentication</product_tag><summary>Test</summary>"
    with patch("app.chat_run", return_value=_fake_chat_events(xml)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")
    events = _parse_sse(resp.data)
    assert events[0] == {"type": "delta", "text": xml}
    done = events[-1]
    assert done["type"] == "done"
    assert "Authentication" in done["response"]
    assert "Test" in done["response"]


def test_history_is_forwarded_to_chat_run(client, mock_jwks, valid_token):
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    xml = "<product_tag>Other</product_tag><summary>ok</summary>"
    with patch("app.chat_run", return_value=_fake_chat_events(xml)) as mock_run:
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
    with patch("app.chat_run", return_value=_fake_chat_events(xml, input_tokens=50, output_tokens=100, latency_ms=77)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    done = _parse_sse(resp.data)[-1]
    assert done["input_tokens"] == 50
    assert done["output_tokens"] == 100
    assert isinstance(done["latency_ms"], int)
    assert done["latency_ms"] >= 0


def test_chat_run_runtime_error_sends_error_event(client, mock_jwks, valid_token):
    """RuntimeError raised while streaming produces an 'error' SSE event, not a done event."""
    def _raising_generator(question, history):
        raise RuntimeError("No response from model")
        yield  # pragma: no cover - makes this a generator function

    with patch("app.chat_run", side_effect=_raising_generator):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    assert events == [{"type": "error", "error": "No response from model"}]
