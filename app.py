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
from flask import Flask, request, jsonify, g, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from dotenv import load_dotenv
import jwt
from chat import stream_run as chat_run

load_dotenv()

# Root handler so WARNING+ reaches stderr in the Vercel function logs. Without it,
# flask-limiter's own logger (which only has a NullHandler) swallows storage
# failures silently — that is how a dead Redis went unnoticed.
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024  # larger bodies get 413 before parsing


@app.errorhandler(413)
def request_too_large(_err):
    return jsonify({"error": "Request too large"}), 413


@app.after_request
def set_api_headers(response):
    """Applies to every response, including errors and SSE streams.

    no-store keeps answers and token-bearing responses out of shared caches.
    nosniff stops browsers from reinterpreting JSON or SSE as another type.
    Headers are set before the body streams, so SSE framing is unaffected.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response

def _load_preview_origin_pattern(raw: str):
    """Compile PREVIEW_ORIGIN_REGEX, or refuse it (returns None).

    An unanchored pattern would match any origin containing the fragment, so it
    is refused rather than trusted. Refused or invalid values disable preview
    CORS and log an error; the rest of the app still starts.
    """
    if not raw:
        return None
    if not (raw.startswith("^") and raw.endswith("$")):
        logger.error(
            "PREVIEW_ORIGIN_REGEX must start with ^ and end with $; refusing it, preview CORS origins are DISABLED"
        )
        return None
    try:
        return re.compile(raw)
    except re.error as e:
        logger.error("PREVIEW_ORIGIN_REGEX is not a valid regex (%s); preview CORS origins are DISABLED", e)
        return None


def _cors_origins_from_env(frontend_origin: str, preview_regex: str) -> list:
    origins: list = []
    if frontend_origin:
        origins.append(frontend_origin)
    pattern = _load_preview_origin_pattern(preview_regex)
    if pattern is not None:
        origins.append(pattern)
    return origins


_frontend_origin = os.getenv("FRONTEND_ORIGIN", "")
_preview_regex = os.getenv("PREVIEW_ORIGIN_REGEX", "")

CORS(
    app,
    origins=_cors_origins_from_env(_frontend_origin, _preview_regex),
    allow_headers=["Authorization", "Content-Type"],
    methods=["POST", "OPTIONS"],
)


def client_ip() -> str:
    # Vercel overwrites X-Forwarded-For with the real client IP, so it is only trusted there.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if os.getenv("VERCEL") and forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


_redis_url = os.getenv("REDIS_URL")
limiter = Limiter(
    client_ip,
    app=app,
    default_limits=[],
    storage_uri=_redis_url if _redis_url else "memory://",
    storage_options={"socket_connect_timeout": 2, "socket_timeout": 2} if _redis_url else {},
    swallow_errors=True,
)


def check_limiter_storage() -> bool:
    """Log which rate-limit storage is active and whether it is reachable.

    The limiter runs with swallow_errors=True (a Redis outage must not take
    /ask down), which fails open: limits silently stop applying. This makes
    that state loud at startup instead of invisible.
    """
    if not _redis_url:
        logger.warning(
            "REDIS_URL not set: rate limits use per-process memory, so each "
            "function instance counts separately and limits are not enforced globally"
        )
        return False
    try:
        healthy = bool(limiter.storage.check())
    except Exception:
        logger.exception("Rate-limit Redis check raised; limits are NOT enforced")
        return False
    if not healthy:
        logger.error("Rate-limit Redis is unreachable; limits are NOT enforced (failing open)")
        return False
    logger.info("Rate-limit storage: Redis reachable")
    return True


class _LimiterFailureWatch(logging.Handler):
    """Turns the first swallowed limiter storage error into one WARNING per process.

    flask-limiter logs every swallowed storage error at ERROR, once per request.
    The limiter fails open, so the first one is the signal an operator needs.
    """

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.tripped = False

    def emit(self, record):
        if self.tripped:
            return
        self.tripped = True
        cause = record.exc_info[1] if record.exc_info else None
        detail = f"{record.getMessage()}: {cause!r}" if cause is not None else record.getMessage()
        logger.warning(
            "Rate limiting is NOT enforced in this process: limiter storage failed (%s). "
            "Requests are being allowed. Check REDIS_URL and Redis health.",
            detail,
        )


_limiter_failure_watch = _LimiterFailureWatch()
logging.getLogger("flask-limiter").addHandler(_limiter_failure_watch)

check_limiter_storage()

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
GUEST_JWT_SECRET = os.getenv("GUEST_JWT_SECRET", "")


_jwks_cache: dict | None = None
_jwks_cached_at: float = 0.0
_jwks_last_attempt_at: float = 0.0
JWKS_TTL = 3600  # 1 hour
JWKS_MIN_FETCH_INTERVAL = 60  # network attempts are spaced at least this far apart


class JWKSUnavailable(OSError):
    """Clerk's signing keys cannot be loaded right now. Surfaces as 503, not 401."""


def _download_jwks() -> dict:
    with urllib.request.urlopen(CLERK_JWKS_URL, timeout=5) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise ValueError("JWKS response has no keys list")
    return data


def _fetch_jwks(force: bool = False) -> dict:
    """Return Clerk's public JWKS, refreshing it from the network when needed.

    The cache is used until JWKS_TTL expires, or until `force` asks for a
    refresh. Network attempts are at least JWKS_MIN_FETCH_INTERVAL apart, so
    tokens with unknown kids cannot turn into a flood of requests to Clerk.
    If a refresh fails and a cache exists, the stale cache is served.
    """
    global _jwks_cache, _jwks_cached_at, _jwks_last_attempt_at
    now = time.time()
    throttled = now - _jwks_last_attempt_at < JWKS_MIN_FETCH_INTERVAL
    if _jwks_cache is not None:
        fresh = now - _jwks_cached_at < JWKS_TTL and not force
        if fresh or throttled:
            return _jwks_cache
    elif throttled:
        # Nothing cached and the last attempt failed moments ago: fail fast
        # instead of letting every request wait on another timeout.
        raise JWKSUnavailable("JWKS unavailable; retrying after the throttle window")

    _jwks_last_attempt_at = now
    try:
        _jwks_cache = _download_jwks()
        _jwks_cached_at = now
    except (OSError, ValueError) as e:
        if _jwks_cache is None:
            raise JWKSUnavailable(f"JWKS fetch failed: {e}") from e
        logger.warning("JWKS refresh failed, keeping cached keys: %s", e)
    return _jwks_cache


def _find_jwk(jwks: dict, kid) -> dict | None:
    return next((k for k in jwks["keys"] if k.get("kid") == kid), None)


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT using the RS256 public key. Returns decoded payload."""
    if not CLERK_JWKS_URL:
        raise RuntimeError("CLERK_JWKS_URL is not configured")

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    key_data = _find_jwk(_fetch_jwks(), kid)
    if key_data is None:
        # Clerk rotates signing keys, so a kid missing from the cache may be new.
        key_data = _find_jwk(_fetch_jwks(force=True), kid)
    if key_data is None:
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
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["HS256", "RS256"])
        return payload.get("role") == "guest"
    except Exception:
        return False


def _user_key() -> str:
    """Return the per-user rate-limit key: Clerk user ID, or client IP for guests.

    Decodes the JWT without verification (require_auth verifies it). Guest tokens
    are minted for free, so each one has a fresh sub. Keying guests on that sub
    would give every new token a new daily bucket, so guests share one bucket per IP.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return client_ip()
    token = auth.split(" ", 1)[1]
    if _is_guest_token(token):
        return f"guest-ip:{client_ip()}"
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get("sub") or client_ip()
    except Exception:
        return client_ip()


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
            except OSError as e:  # URLError and TimeoutError are OSError subclasses
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
@limiter.limit("20 per day", error_message="Guest token daily limit reached")
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


HISTORY_MAX_ITEMS = 20
HISTORY_MAX_CONTENT_CHARS = {"user": 2000, "assistant": 12000}  # assistant turns carry raw XML replies
STREAM_ERROR_MESSAGE = "Something went wrong while answering. Please try again."


def _history_is_valid(history) -> bool:
    """History must be a short list of {role, content} turns with string content."""
    if not isinstance(history, list) or len(history) > HISTORY_MAX_ITEMS:
        return False
    for turn in history:
        if not isinstance(turn, dict):
            return False
        role = turn.get("role")
        if role not in HISTORY_MAX_CONTENT_CHARS:
            return False
        content = turn.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > HISTORY_MAX_CONTENT_CHARS[role]:
            return False
    return True


def _counts_toward_quota(response) -> bool:
    """Per-user and global budgets are charged only for requests that got past auth
    and were not refused by a limit. Otherwise forged or garbage tokens could burn
    a victim's daily quota (the sub claim is read before verification) or the
    global cap for everyone."""
    return response.status_code not in (401, 429, 503)


# flask-limiter checks every limit on this route at the innermost limiter decorator,
# in registration order (bottom-up), stopping at the first breach. So:
# - require_auth sits below the limiter, so the per-IP limits run before auth and
#   count unauthenticated floods;
# - the per-IP daily cap comes before the per-user and global caps, so a refused
#   request never reaches the global counter;
# - the global cap is registered last, so a request refused per-user does not use it.
@app.route("/ask", methods=["POST"])
@limiter.limit("70 per day", key_func=lambda: "global", error_message="Service limit reached",
               deduct_when=_counts_toward_quota)
@limiter.limit("5 per day", key_func=_user_key, error_message="Daily limit reached",
               deduct_when=_counts_toward_quota)
@limiter.limit("30 per day", error_message="IP daily limit reached")
@limiter.limit("20 per minute")
@require_auth
def ask():
    """
    Accepts a JSON body: { "question": "...", "history": [...] }

    Returns a text/event-stream response. Each SSE frame's `data` is one
    JSON-encoded event:
      {"type": "delta", "text": "..."}                 — zero or more
      {"type": "done", "response", "input_tokens",
       "output_tokens", "latency_ms", "chunks"}         — exactly one, on success
      {"type": "error", "error": "..."}                 — instead of "done", on failure

    Each chunk in the chunks list has shape: {"source", "path", "text", "url"}.

    All validation happens before the stream opens, so a bad request still
    gets a plain 4xx JSON response.
    """
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415

    try:
        data = request.get_json(silent=True)
    except (ValueError, RecursionError):
        # Deeply nested JSON can exhaust the decoder's recursion limit.
        return jsonify({"error": "Malformed JSON body"}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    question = data.get("question")
    if not isinstance(question, str):
        return jsonify({"error": "question must be a string"}), 400
    question = question.strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    if len(question) > 2000:
        return jsonify({"error": "Question exceeds 2000 character limit"}), 400

    history = data.get("history", [])
    if not _history_is_valid(history):
        return jsonify({"error": "Invalid history format"}), 400

    def sse(event: dict) -> str:
        return f"data: {json.dumps(event)}\n\n"

    def generate():
        try:
            for event in chat_run(question, history):
                yield sse(event)
        except Exception:
            # Broad on purpose: headers are already committed (200,
            # text/event-stream) by the time this generator runs, so any
            # failure has to become a clean 'error' SSE event instead of an
            # unhandled exception that just aborts the stream. The real
            # exception stays server-side; SDK and upstream messages can
            # carry internal details, so the client gets a fixed string.
            logger.exception("stream_run failed")
            yield sse({"type": "error", "error": STREAM_ERROR_MESSAGE})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


def debug_enabled() -> bool:
    """Werkzeug's debugger allows arbitrary code execution, so it is opt-in only."""
    return os.getenv("FLASK_DEBUG") == "1"


if __name__ == "__main__":
    app.run(debug=debug_enabled(), port=5001)
