"""test_guest_auth.py — Tests for /guest-token endpoint and guest JWT auth on /ask."""

import time
import jwt as pyjwt
from unittest.mock import patch

TEST_GUEST_SECRET = "test-guest-secret-placeholder"


def _fake_chat_result(text="<product_tag>Other</product_tag><summary>ok</summary>"):
    return {"response": text, "input_tokens": 10, "output_tokens": 20, "latency_ms": 42}


# ── /guest-token endpoint ─────────────────────────────────────────────────────

def test_guest_token_returns_200_with_token(client):
    resp = client.get("/guest-token")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "token" in data


def test_guest_token_is_valid_hs256_jwt(client):
    resp = client.get("/guest-token")
    token = resp.get_json()["token"]
    decoded = pyjwt.decode(token, TEST_GUEST_SECRET, algorithms=["HS256"])
    assert decoded["role"] == "guest"
    assert "sub" in decoded
    assert decoded["exp"] > int(time.time())


def test_guest_token_uuids_are_unique(client):
    t1 = client.get("/guest-token").get_json()["token"]
    t2 = client.get("/guest-token").get_json()["token"]
    p1 = pyjwt.decode(t1, TEST_GUEST_SECRET, algorithms=["HS256"])
    p2 = pyjwt.decode(t2, TEST_GUEST_SECRET, algorithms=["HS256"])
    assert p1["sub"] != p2["sub"]


# ── Guest token accepted on /ask ──────────────────────────────────────────────

def test_guest_token_accepted_on_ask(client):
    now = int(time.time())
    payload = {"sub": "guest-uuid-test", "role": "guest", "iat": now, "exp": now + 86400}
    token = pyjwt.encode(payload, TEST_GUEST_SECRET, algorithm="HS256")

    with patch("app.chat_run", return_value=_fake_chat_result()):
        resp = client.post(
            "/ask",
            json={"question": "test?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200


def test_expired_guest_token_returns_401(client):
    now = int(time.time())
    payload = {"sub": "guest-uuid", "role": "guest", "iat": now - 90000, "exp": now - 10}
    token = pyjwt.encode(payload, TEST_GUEST_SECRET, algorithm="HS256")

    resp = client.post(
        "/ask",
        json={"question": "test?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_tampered_guest_token_returns_401(client):
    now = int(time.time())
    payload = {"sub": "guest-uuid", "role": "guest", "iat": now, "exp": now + 86400}
    token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

    resp = client.post(
        "/ask",
        json={"question": "test?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_clerk_token_still_accepted_after_guest_fallback_added(client, mock_jwks, valid_token):
    """Existing Clerk auth path must not be broken by the guest fallback."""
    resp = client.post(
        "/ask",
        content_type="text/plain",
        data="not json",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp.status_code == 415  # reached the route (auth passed), rejected by content-type
