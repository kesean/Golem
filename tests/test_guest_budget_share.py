"""test_guest_budget_share.py — Guests get at most GUEST_DAILY_SHARE of the shared daily budget; signed-in users keep the rest."""

import logging
import time
import uuid
from unittest.mock import patch

import jwt
import pytest


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _guest(app_module):
    now = int(time.time())
    payload = {"sub": str(uuid.uuid4()), "role": "guest", "iat": now, "exp": now + 86400}
    return jwt.encode(payload, app_module.GUEST_JWT_SECRET, algorithm="HS256")


def _fake_chat_result():
    text = "<summary>ok</summary>"
    return [
        {"type": "delta", "text": text},
        {"type": "done", "response": text, "input_tokens": 1, "output_tokens": 1, "latency_ms": 1, "chunks": []},
    ]


def _ask(client, token, ip):
    resp = client.post("/ask", json={"question": "q"}, headers=_auth(token), environ_base={"REMOTE_ADDR": ip})
    resp.get_data()
    return resp


def _prod_global_remaining(app_module):
    return app_module.limiter.limiter.get_window_stats(app_module.GLOBAL_DAILY_LIMIT, "ask-global", "global").remaining


def test_guest_share_exhaustion_refuses_guests_while_signed_in_users_still_pass(rate_limited_client, mock_jwks, conftest_tokens, monkeypatch):
    """Global budget 4, default 50% share: guests get 2. Signed-in users take the remaining 2."""
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "GLOBAL_DAILY_LIMIT", parse("4 per day"))
    with patch("app.chat_run", return_value=_fake_chat_result()):
        assert _ask(rate_limited_client, _guest(app_module), "10.30.0.1").status_code == 200
        assert _ask(rate_limited_client, _guest(app_module), "10.30.0.2").status_code == 200

        guest_refused = _ask(rate_limited_client, _guest(app_module), "10.30.0.3")
        assert guest_refused.status_code == 429
        assert b"Service limit reached" in guest_refused.data
        # The refused guest never touched the global budget.
        assert _prod_global_remaining(app_module) == 2

        assert _ask(rate_limited_client, conftest_tokens[0], "10.30.0.4").status_code == 200
        assert _ask(rate_limited_client, conftest_tokens[1], "10.30.0.5").status_code == 200
        clerk_refused = _ask(rate_limited_client, conftest_tokens[2], "10.30.0.6")
    assert clerk_refused.status_code == 429
    assert b"Service limit reached" in clerk_refused.data
    assert _prod_global_remaining(app_module) == 0


def test_configured_share_changes_the_guest_ceiling(rate_limited_client, mock_jwks, conftest_tokens, monkeypatch):
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "GLOBAL_DAILY_LIMIT", parse("8 per day"))
    monkeypatch.setattr(app_module, "GUEST_DAILY_SHARE", 0.25)
    with patch("app.chat_run", return_value=_fake_chat_result()):
        statuses = [_ask(rate_limited_client, _guest(app_module), f"10.31.0.{i}").status_code for i in range(3)]
    assert statuses == [200, 200, 429]


def test_preview_bucket_is_shared_with_guests_by_the_same_share(rate_limited_client, mock_jwks, conftest_tokens, monkeypatch):
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "PREVIEW_GLOBAL_DAILY_LIMIT", parse("4 per day"))
    monkeypatch.setattr(app_module, "_frontend_origin", "https://golem-support.vercel.app")
    monkeypatch.setattr(app_module, "_preview_origin_pattern", app_module._load_preview_origin_pattern(r"^https://golem-[a-z0-9-]+\.vercel\.app$"))
    preview = "https://golem-abc123.vercel.app"

    def ask(token, ip):
        resp = rate_limited_client.post(
            "/ask", json={"question": "q"}, headers={**_auth(token), "Origin": preview},
            environ_base={"REMOTE_ADDR": ip},
        )
        resp.get_data()
        return resp.status_code

    with patch("app.chat_run", return_value=_fake_chat_result()):
        statuses = [ask(_guest(app_module), f"10.32.0.{i}") for i in range(3)]
    assert statuses == [200, 200, 429]


@pytest.mark.parametrize("raw,expected", [("", 0.5), ("0.25", 0.25), ("1", 1.0), ("0", 0.5), ("1.5", 0.5), ("-1", 0.5), ("lots", 0.5), ("nan", 0.5)])
def test_guest_share_env_parsing_falls_back_to_default(monkeypatch, caplog, raw, expected):
    import app as app_module

    monkeypatch.setenv("GUEST_DAILY_SHARE", raw)
    with caplog.at_level(logging.ERROR, logger="app"):
        assert app_module._guest_daily_share() == expected
    logged = any("GUEST_DAILY_SHARE" in r.message for r in caplog.records)
    assert logged == (raw not in ("", "0.25", "1"))


def test_guest_cap_is_share_of_the_budget_with_a_floor_of_one(monkeypatch):
    import app as app_module
    from limits import parse

    monkeypatch.setattr(app_module, "GUEST_DAILY_SHARE", 0.5)
    assert app_module._guest_cap(parse("70 per day")).amount == 35
    assert app_module._guest_cap(parse("1 per day")).amount == 1
