"""test_rate_limits.py — Tests for per-user, per-IP and global rate limits on /ask and /guest-token."""

import time
import uuid
from unittest.mock import patch

import jwt
import pytest


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class FakeClock:
    """Stands in for time.time() so tests can cross fixed-window boundaries."""

    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock(time.time())
    monkeypatch.setattr(time, "time", fake)
    return fake


def _guest_token(clock):
    import app as app_module
    now = int(clock())
    payload = {"sub": str(uuid.uuid4()), "role": "guest", "iat": now, "exp": now + 86400}
    return jwt.encode(payload, app_module.GUEST_JWT_SECRET, algorithm="HS256")


def _fake_chat_result(text="<summary>ok</summary>"):
    """Events matching the shape chat.stream_run() yields."""
    return [
        {"type": "delta", "text": text},
        {"type": "done", "response": text, "input_tokens": 10, "output_tokens": 20, "latency_ms": 42, "chunks": []},
    ]


def test_per_user_limit_returns_429_after_5_requests(rate_limited_client, mock_jwks, valid_token):
    """The 6th request from the same user in a day should return 429."""
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(5):
            resp = rate_limited_client.post(
                "/ask",
                json={"question": "test?"},
                headers=_auth_headers(valid_token),
            )
            assert resp.status_code == 200
            resp.get_data()  # fully consume the SSE stream so its request context is popped

        resp = rate_limited_client.post(
            "/ask",
            json={"question": "one too many"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 429
    assert b"Daily limit reached" in resp.data


def test_global_limit_returns_429_after_70_requests(rate_limited_client, mock_jwks, conftest_tokens):
    """The 71st request globally in a day should return 429.

    Each request uses a unique IP and a unique user sub so that neither the
    per-IP (20/min) nor per-user (5/day) limits fire before the global cap.
    """
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for i, token in enumerate(conftest_tokens[:70]):
            resp = rate_limited_client.post(
                "/ask",
                json={"question": "test?"},
                headers=_auth_headers(token),
                environ_base={"REMOTE_ADDR": f"10.0.{i // 256}.{i % 256}"},
            )
            assert resp.status_code == 200
            resp.get_data()  # fully consume the SSE stream so its request context is popped

        resp = rate_limited_client.post(
            "/ask",
            json={"question": "over the global cap"},
            headers=_auth_headers(conftest_tokens[70]),
            environ_base={"REMOTE_ADDR": "10.1.0.0"},
        )
    assert resp.status_code == 429
    assert b"Service limit reached" in resp.data


def test_garbage_token_flood_is_rate_limited_before_auth(rate_limited_client, clock):
    """Unauthenticated garbage counts toward the per-IP limit: 401s run out into 429s."""
    for _ in range(20):
        resp = rate_limited_client.post(
            "/ask", json={"question": "q"}, headers=_auth_headers("not-a-jwt"),
        )
        assert resp.status_code == 401
    resp = rate_limited_client.post(
        "/ask", json={"question": "q"}, headers=_auth_headers("not-a-jwt"),
    )
    assert resp.status_code == 429


def test_forged_tokens_cannot_use_up_a_victims_daily_quota(rate_limited_client, mock_jwks, clock, conftest_tokens):
    """The per-user key is read before verification, so a forged token that
    claims a victim's sub must fail auth without charging the victim's bucket."""
    forged = jwt.encode({"sub": "user_0"}, "not-the-signing-key", algorithm="HS256")
    for i in range(10):
        resp = rate_limited_client.post(
            "/ask", json={"question": "q"}, headers=_auth_headers(forged),
            environ_base={"REMOTE_ADDR": f"10.4.0.{i}"},
        )
        assert resp.status_code == 401

    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(5):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(conftest_tokens[0]),
                environ_base={"REMOTE_ADDR": "10.4.9.9"},
            )
            resp.get_data()
            assert resp.status_code == 200


def test_fresh_guest_tokens_share_one_daily_bucket_per_ip(rate_limited_client, clock):
    """Minting a new guest token must not reset the guest daily limit for that IP."""
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(5):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"},
                headers=_auth_headers(_guest_token(clock)),
                environ_base={"REMOTE_ADDR": "10.8.0.1"},
            )
            assert resp.status_code == 200
            resp.get_data()
        resp = rate_limited_client.post(
            "/ask", json={"question": "one too many"},
            headers=_auth_headers(_guest_token(clock)),
            environ_base={"REMOTE_ADDR": "10.8.0.1"},
        )
    assert resp.status_code == 429
    assert b"Daily limit reached" in resp.data


def test_guest_daily_limit_does_not_apply_to_other_ips(rate_limited_client, clock):
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(5):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"},
                headers=_auth_headers(_guest_token(clock)),
                environ_base={"REMOTE_ADDR": "10.8.0.2"},
            )
            resp.get_data()
        resp = rate_limited_client.post(
            "/ask", json={"question": "q"},
            headers=_auth_headers(_guest_token(clock)),
            environ_base={"REMOTE_ADDR": "10.8.0.3"},
        )
    assert resp.status_code == 200
    resp.get_data()


def test_guest_token_mints_capped_per_ip_per_day(rate_limited_client, clock):
    """10/hour still applies; a day's worth of mints from one IP stops at 20."""
    def mint():
        return rate_limited_client.get("/guest-token", environ_base={"REMOTE_ADDR": "10.7.0.1"})

    for _ in range(10):
        assert mint().status_code == 200
    clock.advance(3600)
    for _ in range(10):
        assert mint().status_code == 200
    clock.advance(3600)
    resp = mint()
    assert resp.status_code == 429
    assert b"Guest token daily limit reached" in resp.data


def test_ask_per_ip_daily_cap_is_30(rate_limited_client, mock_jwks, clock, conftest_tokens):
    """One IP gets 30 /ask requests a day, even with a fresh user on every request."""
    with patch("app.chat_run", return_value=_fake_chat_result()):
        statuses = []
        for i, token in enumerate(conftest_tokens[:31]):
            if i == 20:
                clock.advance(61)  # clear the 20/minute window; only the daily cap can fire now
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(token),
                environ_base={"REMOTE_ADDR": "10.6.0.1"},
            )
            resp.get_data()
            statuses.append(resp.status_code)
        last = resp
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429
    assert b"IP daily limit reached" in last.data


def test_rejected_requests_do_not_consume_global_cap(rate_limited_client, mock_jwks, clock, conftest_tokens):
    """One IP that hammers /ask must not use up the 70/day global budget for everyone else.

    IP A sends 40 requests (30 may pass, the rest hit the per-IP daily cap).
    Then 40 requests from fresh IPs must all pass, and the 41st must hit the
    global cap. If A's rejected requests were counted globally, this fails early.
    """
    tokens = conftest_tokens
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for i in range(40):
            if i == 20:
                clock.advance(61)
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(tokens[i]),
                environ_base={"REMOTE_ADDR": "10.5.0.1"},
            )
            resp.get_data()

        # Subs repeat across the next batch but each stays under its own 5/day user cap.
        for j in range(40):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(tokens[j % 71]),
                environ_base={"REMOTE_ADDR": f"10.5.1.{j}"},
            )
            resp.get_data()
            assert resp.status_code == 200, f"fresh IP {j} was refused"

        resp = rate_limited_client.post(
            "/ask", json={"question": "q"}, headers=_auth_headers(tokens[40]),
            environ_base={"REMOTE_ADDR": "10.5.2.0"},
        )
    assert resp.status_code == 429
    assert b"Service limit reached" in resp.data
