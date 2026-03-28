"""
conftest.py — Shared fixtures for the backend test suite.

Env vars must be set BEFORE app.py is imported because CLERK_JWKS_URL and
ANTHROPIC_API_KEY are read at module-import time in app.py.
"""

import os
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import jwt

# ── Set env vars before importing the Flask app ──────────────────────────────
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-placeholder")
os.environ.setdefault("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")

# ── Generate a test RSA key pair once per session ────────────────────────────
_RSA_PRIVATE = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)
_RSA_PUBLIC = _RSA_PRIVATE.public_key()

_PUBLIC_JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(_RSA_PUBLIC))
_PUBLIC_JWK.update({"kid": "test-kid", "use": "sig", "alg": "RS256"})
FAKE_JWKS = {"keys": [_PUBLIC_JWK]}


def _make_token(*, expired: bool = False, wrong_kid: bool = False) -> str:
    """Sign a JWT with the test RSA key."""
    now = int(time.time())
    payload = {
        "sub": "user_test123",
        "iss": "https://test.clerk.dev",
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
    }
    kid = "wrong-kid" if wrong_kid else "test-kid"
    return jwt.encode(payload, _RSA_PRIVATE, algorithm="RS256", headers={"kid": kid})


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Flask test client with testing mode and rate limiter disabled."""
    from app import app, limiter  # imported here so env vars are set first
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    with app.test_client() as c:
        yield c


@pytest.fixture
def valid_token():
    return _make_token()


@pytest.fixture
def expired_token():
    return _make_token(expired=True)


@pytest.fixture
def mock_jwks(monkeypatch):
    """Patch _fetch_jwks so auth succeeds without a real Clerk endpoint."""
    import app as app_module
    monkeypatch.setattr(app_module, "_fetch_jwks", lambda: FAKE_JWKS)
