"""
app.py — Flask app and API routes.
"""

import os
import re
import json
import time
import uuid
import logging
import urllib.request
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import jwt
from chat import run as chat_run

load_dotenv()

app = Flask(__name__)

_frontend_origin = os.getenv("FRONTEND_ORIGIN", "")
_preview_regex = os.getenv("PREVIEW_ORIGIN_REGEX", "")

_cors_origins: list = []
if _frontend_origin:
    _cors_origins.append(_frontend_origin)
if _preview_regex:
    _cors_origins.append(re.compile(_preview_regex))

CORS(
    app,
    origins=_cors_origins if _cors_origins else [],
    allow_headers=["Authorization", "Content-Type"],
    methods=["POST", "OPTIONS"],
)

_redis_url = os.getenv("REDIS_URL")
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=_redis_url if _redis_url else "memory://",
    storage_options={"socket_connect_timeout": 2, "socket_timeout": 2} if _redis_url else {},
    swallow_errors=True,
)
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
GUEST_JWT_SECRET = os.getenv("GUEST_JWT_SECRET", "")


_jwks_cache: dict | None = None
_jwks_cached_at: float = 0.0
JWKS_TTL = 3600  # 1 hour


def _fetch_jwks() -> dict:
    """Fetch Clerk's public JWKS, cached for JWKS_TTL seconds."""
    global _jwks_cache, _jwks_cached_at
    if _jwks_cache and time.time() - _jwks_cached_at < JWKS_TTL:
        return _jwks_cache
    with urllib.request.urlopen(CLERK_JWKS_URL, timeout=5) as resp:
        _jwks_cache = json.loads(resp.read())
        _jwks_cached_at = time.time()
    return _jwks_cache


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT using the RS256 public key. Returns decoded payload."""
    if not CLERK_JWKS_URL:
        raise RuntimeError("CLERK_JWKS_URL is not configured")

    jwks = _fetch_jwks()
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    key_data = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key_data:
        raise ValueError("No matching JWK found for kid: " + str(kid))

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
    return jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})


def verify_guest_token(token: str) -> dict:
    """Verify a guest JWT signed with GUEST_JWT_SECRET (HS256)."""
    if not GUEST_JWT_SECRET:
        raise RuntimeError("GUEST_JWT_SECRET is not configured")
    payload = jwt.decode(token, GUEST_JWT_SECRET, algorithms=["HS256"])
    if payload.get("role") != "guest":
        raise ValueError("Token is not a guest token")
    return payload


def _is_guest_token(token: str) -> bool:
    """Peek at the token's role claim without verification to route to the right verifier."""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get("role") == "guest"
    except Exception:
        return False


def _user_key() -> str:
    """Return Clerk user ID for per-user rate limiting, falls back to IP.

    Decodes the JWT without verification — auth is enforced separately by
    require_auth. We only need the sub claim as a stable per-user key.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return get_remote_address()
    try:
        payload = jwt.decode(
            auth.split(" ", 1)[1],
            options={"verify_signature": False},
        )
        return payload.get("sub") or get_remote_address()
    except Exception:
        return get_remote_address()


def require_auth(f):
    """Decorator that enforces Clerk JWT auth or guest JWT auth on a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth_header.split(" ", 1)[1]

        if _is_guest_token(token):
            try:
                g.clerk_payload = verify_guest_token(token)
            except jwt.ExpiredSignatureError:
                logging.warning("Rejected expired guest JWT")
                return jsonify({"error": "Token expired"}), 401
            except Exception as e:
                logging.warning("Invalid guest token: %s", e)
                return jsonify({"error": "Invalid or expired token"}), 401
        else:
            try:
                g.clerk_payload = verify_clerk_token(token)
            except urllib.error.URLError as e:
                logging.error("JWKS fetch failed: %s", e)
                return jsonify({"error": "Auth service unavailable"}), 503
            except jwt.ExpiredSignatureError:
                logging.warning("Rejected expired JWT")
                return jsonify({"error": "Token expired"}), 401
            except jwt.DecodeError as e:
                logging.warning("Malformed JWT: %s", e)
                return jsonify({"error": "Invalid token"}), 401
            except Exception as e:
                logging.error("Unexpected auth error: %s", e)
                return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)
    return decorated


@app.route("/guest-token", methods=["GET"])
@limiter.limit("10 per hour")
def guest_token():
    if not GUEST_JWT_SECRET:
        return jsonify({"error": "Guest access not configured"}), 503
    now = int(time.time())
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "guest",
        "iat": now,
        "exp": now + 86400,
    }
    token = jwt.encode(payload, GUEST_JWT_SECRET, algorithm="HS256")
    return jsonify({"token": token})


@app.route("/ask", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
@limiter.limit("5 per day", key_func=_user_key, error_message="Daily limit reached")
@limiter.limit("70 per day", key_func=lambda: "global", error_message="Service limit reached")
def ask():
    """
    Accepts a JSON body: { "question": "...", "history": [...] }
    Returns a JSON response: { "response": "<xml>...", "input_tokens": int, "output_tokens": int, "latency_ms": int }
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    data = request.get_json()
    question = data.get("question", "").strip()
    history  = data.get("history", [])

    if not question:
        return jsonify({"error": "No question provided"}), 400

    if len(question) > 2000:
        return jsonify({"error": "Question exceeds 2000 character limit"}), 400

    if not isinstance(history, list):
        return jsonify({"error": "Invalid history format"}), 400

    try:
        result = chat_run(question, history)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
