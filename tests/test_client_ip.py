import app as app_module
from app import app, client_ip


def _ip(monkeypatch, vercel, headers, remote="10.0.0.1"):
    if vercel:
        monkeypatch.setenv("VERCEL", "1")
    else:
        monkeypatch.delenv("VERCEL", raising=False)
    with app.test_request_context(headers=headers, environ_base={"REMOTE_ADDR": remote}):
        return client_ip()


def test_uses_forwarded_for_on_vercel(monkeypatch):
    assert _ip(monkeypatch, True, {"X-Forwarded-For": "203.0.113.7"}) == "203.0.113.7"


def test_takes_leftmost_forwarded_for_entry(monkeypatch):
    assert _ip(monkeypatch, True, {"X-Forwarded-For": "203.0.113.7, 10.0.0.2"}) == "203.0.113.7"


def test_ignores_forwarded_for_off_vercel(monkeypatch):
    assert _ip(monkeypatch, False, {"X-Forwarded-For": "203.0.113.7"}) == "10.0.0.1"


def test_falls_back_to_remote_addr_without_header(monkeypatch):
    assert _ip(monkeypatch, True, {}) == "10.0.0.1"


def test_guest_token_limit_is_per_client_on_vercel(monkeypatch, rate_limited_client):
    client = rate_limited_client
    monkeypatch.setenv("VERCEL", "1")
    a = {"X-Forwarded-For": "203.0.113.7"}
    b = {"X-Forwarded-For": "198.51.100.9"}
    for _ in range(10):
        assert client.get("/guest-token", headers=a).status_code == 200
    assert client.get("/guest-token", headers=a).status_code == 429
    assert client.get("/guest-token", headers=b).status_code == 200
