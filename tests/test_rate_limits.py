"""test_rate_limits.py — Tests for per-user and global rate limits on /ask."""

from unittest.mock import MagicMock, patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_message(text="<summary>ok</summary>"):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_per_user_limit_returns_429_after_10_requests(rate_limited_client, mock_jwks, valid_token):
    """The 11th request from the same user in a day should return 429."""
    with patch("app.client.messages.create", return_value=_fake_message()):
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
