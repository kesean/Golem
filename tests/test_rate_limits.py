"""test_rate_limits.py — Tests for per-user and global rate limits on /ask."""

from unittest.mock import patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_chat_result(text="<summary>ok</summary>"):
    return {"response": text, "input_tokens": 10, "output_tokens": 20, "latency_ms": 42}


def test_per_user_limit_returns_429_after_10_requests(rate_limited_client, mock_jwks, valid_token):
    """The 11th request from the same user in a day should return 429."""
    with patch("app.chat_run", return_value=_fake_chat_result()):
        for _ in range(10):
            resp = rate_limited_client.post(
                "/ask",
                json={"question": "test?"},
                headers=_auth_headers(valid_token),
            )
            assert resp.status_code == 200

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
    per-IP (20/min) nor per-user (10/day) limits fire before the global cap.
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

        # 71st request — global cap should fire
        resp = rate_limited_client.post(
            "/ask",
            json={"question": "over the global cap"},
            headers=_auth_headers(conftest_tokens[70]),
            environ_base={"REMOTE_ADDR": "10.1.0.0"},
        )
    assert resp.status_code == 429
    assert b"Service limit reached" in resp.data
