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


def test_parallel_guest_requests_cannot_exceed_daily_limit(rate_limited_client, clock):
    """Six requests pass auth at the same moment: exactly five are answered, one is refused.

    The barrier holds every request after auth and before the charge. A
    check-then-count split would let all six through; an atomic hit does not.
    """
    import threading
    import app as app_module

    real_verify = app_module.verify_guest_token
    real_test = app_module.limiter.limiter.test
    barrier = threading.Barrier(6, timeout=5)

    def verify_then_wait(token):
        payload = real_verify(token)
        barrier.wait()
        return payload

    def test_then_wait(*args, **kwargs):
        # Only a check-then-count split calls test(); holding every thread between
        # its check and its count is what would let all six through.
        result = real_test(*args, **kwargs)
        barrier.wait()
        return result

    tokens = [_guest_token(clock) for _ in range(6)]
    statuses = []
    lock = threading.Lock()

    def worker(token):
        with app_module.app.test_client() as client:
            resp = client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(token),
                environ_base={"REMOTE_ADDR": "10.3.0.1"},
            )
            resp.get_data()
            with lock:
                statuses.append(resp.status_code)

    with patch.object(app_module, "verify_guest_token", verify_then_wait), \
         patch.object(app_module.limiter.limiter, "test", side_effect=test_then_wait), \
         patch("app.chat_run", return_value=_fake_chat_result()):
        threads = [threading.Thread(target=worker, args=(t,)) for t in tokens]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

    assert sorted(statuses) == [200] * 5 + [429]


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


def test_signed_in_ip_backstop_is_200_per_day(rate_limited_client, mock_jwks, clock, conftest_tokens, monkeypatch):
    """Signed-in users are capped per user. The per-IP daily figure is a loose 200 backstop.
    The global cap is raised here so that it cannot fire first."""
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "GLOBAL_DAILY_LIMIT", parse("1000 per day"))
    statuses = []
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for i in range(201):
            if i and i % 20 == 0:
                clock.advance(61)  # clear the per-minute window; only the daily backstop can fire
            # 71 subs reused: each sub appears at most 3 times, under its own 5/day cap.
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(conftest_tokens[i % 71]),
                environ_base={"REMOTE_ADDR": "10.6.0.1"},
            )
            resp.get_data()
            statuses.append(resp.status_code)
    assert statuses[:200] == [200] * 200
    assert statuses[200] == 429
    assert b"IP daily limit reached" in resp.data


def test_guest_ip_cap_is_10_per_day(rate_limited_client, clock, monkeypatch):
    """Guests get 10 /ask requests a day per IP. The per-user cap is raised so only the IP cap can fire."""
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "USER_DAILY_LIMIT", parse("100 per day"))
    statuses = []
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(11):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(_guest_token(clock)),
                environ_base={"REMOTE_ADDR": "10.2.0.1"},
            )
            resp.get_data()
            statuses.append(resp.status_code)
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
    assert b"IP daily limit reached" in resp.data


def test_per_user_refusal_does_not_use_global_budget(rate_limited_client, mock_jwks, conftest_tokens):
    """A user refused by the per-user cap never reaches the global budget."""
    import app as app_module

    statuses = []
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(6):
            resp = rate_limited_client.post(
                "/ask", json={"question": "q"}, headers=_auth_headers(conftest_tokens[0]),
                environ_base={"REMOTE_ADDR": "10.5.0.1"},
            )
            resp.get_data()
            statuses.append(resp.status_code)
    assert statuses == [200] * 5 + [429]
    remaining = app_module.limiter.limiter.get_window_stats(app_module.GLOBAL_DAILY_LIMIT, "ask-global", "global").remaining
    assert remaining == 65


def test_invalid_requests_do_not_use_daily_quota(rate_limited_client, mock_jwks, valid_token):
    """400s are refused before the quota is charged, so bad requests cost nothing."""
    for _ in range(10):
        resp = rate_limited_client.post("/ask", json={"question": ""}, headers=_auth_headers(valid_token))
        assert resp.status_code == 400
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(5):
            resp = rate_limited_client.post("/ask", json={"question": "q"}, headers=_auth_headers(valid_token))
            resp.get_data()
            assert resp.status_code == 200


def test_user_is_charged_when_only_the_global_cap_refuses(rate_limited_client, mock_jwks, conftest_tokens, monkeypatch):
    """User B passes the per-user check, then the global cap refuses. B is still charged."""
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "GLOBAL_DAILY_LIMIT", parse("1 per day"))
    with patch("app.chat_run", return_value=_fake_chat_result()):
        first = rate_limited_client.post("/ask", json={"question": "q"}, headers=_auth_headers(conftest_tokens[0]))
        first.get_data()
        assert first.status_code == 200
        refused = rate_limited_client.post("/ask", json={"question": "q"}, headers=_auth_headers(conftest_tokens[1]))
    assert refused.status_code == 429
    assert b"Service limit reached" in refused.data

    remaining = app_module.limiter.limiter.get_window_stats(app_module.USER_DAILY_LIMIT, "ask-user", "user_1").remaining
    assert remaining == 4


def test_storage_error_inside_charge_fails_open_with_one_warning(rate_limited_client, mock_jwks, valid_token, monkeypatch, caplog):
    import logging
    from unittest.mock import patch as mock_patch
    import app as app_module

    monkeypatch.setattr(app_module._limiter_failure_watch, "tripped", False)
    with patch("app.chat_run", return_value=_fake_chat_result()), \
         mock_patch.object(app_module.limiter.limiter, "hit", side_effect=ConnectionError("redis down")), \
         caplog.at_level(logging.WARNING, logger="app"):
        for _ in range(2):
            resp = rate_limited_client.post("/ask", json={"question": "q"}, headers=_auth_headers(valid_token))
            resp.get_data()
            assert resp.status_code == 200
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "NOT enforced" in r.message]
    assert len(warnings) == 1
    assert any("Failed to charge rate limit" in r.message for r in caplog.records if r.levelno == logging.ERROR)
