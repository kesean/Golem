"""
app.py — Flask app and API routes.

Phase 3: /ask/stream streams raw text chunks, frontend parses XML on completion.
"""

import os
import json
import time
import urllib.request
from functools import wraps
from flask import Flask, request, jsonify, Response, stream_with_context, g
from anthropic import Anthropic
from dotenv import load_dotenv
import jwt
from prompt import SYSTEM_PROMPT, build_messages

load_dotenv()

app = Flask(__name__)
client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment automatically

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")


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


def require_auth(f):
    """Decorator that enforces Clerk JWT auth on a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            g.clerk_payload = verify_clerk_token(token)
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/ask/stream", methods=["POST"])
@require_auth
def ask_stream():
    """
    Accepts a JSON body: { "question": "..." }
    Streams raw text chunks from Claude as text/plain.
    Frontend accumulates chunks, then parses the JSON and renders structured sections.
    """
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=build_messages(question),
        ) as stream:
            for text in stream.text_stream:
                yield text

    return Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
