"""test_ask_logging.py — Every authenticated /ask logs ip, auth kind and a hashed sub, never the question or the token."""

import hashlib
import logging
import time
import uuid
from unittest.mock import patch

import jwt

SECRET_QUESTION = "what is the secret quarterly roadmap"


def _fake_chat_result():
    text = "<summary>ok</summary>"
    return [
        {"type": "delta", "text": text},
        {"type": "done", "response": text, "input_tokens": 1, "output_tokens": 1, "latency_ms": 1, "chunks": []},
    ]


def _digest(sub):
    return hashlib.sha256(sub.encode()).hexdigest()[:16]


def _ask_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "app" and r.getMessage().startswith("ask ")]


def test_clerk_ask_is_logged_with_hashed_sub_and_no_question(client, mock_jwks, valid_token, caplog):
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         caplog.at_level(logging.INFO, logger="app"):
        resp = client.post(
            "/ask", json={"question": SECRET_QUESTION},
            headers={"Authorization": f"Bearer {valid_token}"}, environ_base={"REMOTE_ADDR": "203.0.113.9"},
        )
        resp.get_data()
    assert resp.status_code == 200
    lines = _ask_lines(caplog)
    assert len(lines) == 1
    assert "ip=203.0.113.9" in lines[0]
    assert "kind=clerk" in lines[0]
    assert f"sub={_digest('user_test123')}" in lines[0]
    assert "user_test123" not in lines[0]
    assert SECRET_QUESTION not in caplog.text
    assert valid_token not in caplog.text


def test_guest_ask_is_logged_as_guest(client, caplog):
    import app as app_module

    now = int(time.time())
    guest_sub = str(uuid.uuid4())
    token = jwt.encode({"sub": guest_sub, "role": "guest", "iat": now, "exp": now + 3600}, app_module.GUEST_JWT_SECRET, algorithm="HS256")
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         caplog.at_level(logging.INFO, logger="app"):
        resp = client.post(
            "/ask", json={"question": SECRET_QUESTION},
            headers={"Authorization": f"Bearer {token}"}, environ_base={"REMOTE_ADDR": "198.51.100.4"},
        )
        resp.get_data()
    assert resp.status_code == 200
    lines = _ask_lines(caplog)
    assert len(lines) == 1
    assert "ip=198.51.100.4" in lines[0]
    assert "kind=guest" in lines[0]
    assert guest_sub not in caplog.text
    assert token not in caplog.text
    assert SECRET_QUESTION not in caplog.text
