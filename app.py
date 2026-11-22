"""
app.py — Flask app and API routes.
"""

import os
import re
import json
import math
import time
import uuid
import hashlib
import logging
import urllib.parse
import urllib.request
from functools import wraps
from flask import Flask, request, jsonify, g, Response, stream_with_context
from flask_cors import CORS
from flask_limiter import Limiter
from dotenv import load_dotenv
from limits import parse
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
    """Compile PREVIEW_ORIGIN_REGEX so it must match the whole origin (None if unusable).

    The value is wrapped as \\A(?:...)\\Z, so an alternation such as `^a|b$` cannot
    match only part of an origin. An unanchored value still works, but it is
    logged as normalised. An invalid regex disables preview CORS and logs an error;
    the rest of the app still starts.
    """
    if not raw:
        return None
    if not (raw.startswith("^") and raw.endswith("$")):
        logger.warning(
            "PREVIEW_ORIGIN_REGEX does not start with ^ and end with $; it is normalised to match the whole origin"
        )
    try:
        return re.compile(rf"\A(?:{raw})\Z")
    except re.error as e:
        logger.error("PREVIEW_ORIGIN_REGEX is not a valid regex (%s); preview CORS origins are DISABLED", e)
        return None


def _cors_origins_from_env(frontend_origin: str, pattern) -> list:
    origins: list = []
    if frontend_origin:
        origins.append(frontend_origin)
    if pattern is not None:
        origins.append(pattern)
    return origins


_frontend_origin = os.getenv("FRONTEND_ORIGIN", "")
_preview_origin_pattern = _load_preview_origin_pattern(os.getenv("PREVIEW_ORIGIN_REGEX", ""))
if not _frontend_origin and _preview_origin_pattern is not None:
    logger.warning(
        "FRONTEND_ORIGIN is unset while PREVIEW_ORIGIN_REGEX is set: the prod frontend's Origin "
        "may match the regex and be charged to the preview bucket. Set FRONTEND_ORIGIN to the exact prod origin."
    )

CORS(
    app,
    origins=_cors_origins_from_env(_frontend_origin, _preview_origin_pattern),
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

    The per-minute and guest-token limiters run with swallow_errors=True (a
    Redis outage must not take those routes down), so their limits stop applying
    while Redis is unavailable. /ask stays fail-closed: it returns 503 unless its
    daily quota can be charged. This makes the limiter state loud at startup
    instead of invisible.
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
        logger.error("Rate-limit Redis is unreachable; per-minute and guest-token limits are NOT enforced (/ask returns 503)")
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
            "Per-minute and guest-token rate limits are NOT enforced in this process: limiter storage failed (%s). "
            "Those requests are allowed through; /ask answers are refused with 503 "
            "until the daily quota can be charged. Check REDIS_URL and Redis health.",
            detail,
        )


_limiter_failure_watch = _LimiterFailureWatch()
logging.getLogger("flask-limiter").addHandler(_limiter_failure_watch)

check_limiter_storage()

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
GUEST_JWT_SECRET = os.getenv("GUEST_JWT_SECRET", "")
GUEST_SECRET_MIN_LENGTH = 32

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT = 5  # seconds; a slow verify must not hold a guest request open
TURNSTILE_TOKEN_MAX_LENGTH = 2048


def _is_production() -> bool:
    return os.getenv("VERCEL_ENV") == "production"


def check_startup_config(env) -> None:
    """Refuse to start with config that would silently disable cost controls.

    On Vercel the daily budgets are only shared across instances when REDIS_URL
    is set, and guest tokens need a real signing secret. Off Vercel, an unset
    GUEST_JWT_SECRET only disables guest access (see guest_token).
    """
    on_prod = env.get("VERCEL_ENV") == "production"
    if on_prod and not env.get("REDIS_URL"):
        raise RuntimeError(
            "REDIS_URL is required on Vercel: without it rate limits and daily cost caps are per-process and not enforced"
        )
    secret = env.get("GUEST_JWT_SECRET", "")
    if not secret:
        if on_prod:
            raise RuntimeError("GUEST_JWT_SECRET is required on Vercel")
        return
    if len(secret) < GUEST_SECRET_MIN_LENGTH:
        raise RuntimeError(
            f"GUEST_JWT_SECRET must be at least {GUEST_SECRET_MIN_LENGTH} characters (got {len(secret)}). "
            'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if on_prod and not env.get("TURNSTILE_SECRET_KEY"):
        raise RuntimeError(
            "TURNSTILE_SECRET_KEY is required on Vercel production: guest tokens are only issued after bot verification"
        )


check_startup_config(os.environ)


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


def _sub_fingerprint(sub) -> str:
    """Short SHA-256 of the token subject, so logs can correlate requests without storing the user ID."""
    if not sub:
        return "none"
    return hashlib.sha256(str(sub).encode()).hexdigest()[:16]


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


class TurnstileUnavailable(OSError):
    """Cloudflare gave no usable answer (timeout, network error, bad response). Surfaces as 503."""


def _post_turnstile(form: dict) -> dict:
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(TURNSTILE_VERIFY_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=TURNSTILE_TIMEOUT) as resp:
        return json.loads(resp.read())


def verify_turnstile(token: str, remoteip: str) -> bool:
    """True when Cloudflare accepts the token. Raises TurnstileUnavailable when no answer comes back."""
    form = {"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": remoteip}
    try:
        data = _post_turnstile(form)
    except (OSError, ValueError) as e:  # URLError and timeouts are OSError; bad JSON is ValueError
        raise TurnstileUnavailable(str(e)) from e
    if not isinstance(data, dict):
        raise TurnstileUnavailable("siteverify response is not an object")
    return data.get("success") is True


def _turnstile_refusal():
    """Return an error response when the guest-token request fails bot verification, else None."""
    if not TURNSTILE_SECRET_KEY:
        if _is_production():
            # Startup refuses this config; refuse here too rather than mint unverified tokens.
            return jsonify({"error": "Bot verification not configured"}), 503
        logger.warning("TURNSTILE_SECRET_KEY not set: skipping bot verification for guest tokens (off production only)")
        return None
    body = request.get_json(silent=True)
    token = body.get("turnstile_token") if isinstance(body, dict) else None
    if not isinstance(token, str) or not token or len(token) > TURNSTILE_TOKEN_MAX_LENGTH:
        return jsonify({"error": "Bot verification required"}), 403
    try:
        accepted = verify_turnstile(token, client_ip())
    except TurnstileUnavailable as e:
        logger.error("Turnstile verification unavailable, refusing guest token: %s", e)
        return jsonify({"error": "Bot verification unavailable"}), 503
    if not accepted:
        logger.warning("Turnstile rejected a guest token request")
        return jsonify({"error": "Bot verification failed"}), 403
    return None


@app.route("/guest-token", methods=["POST"])
@limiter.limit("10 per hour")
@limiter.limit("20 per day", error_message="Guest token daily limit reached")
def guest_token():
    if not GUEST_JWT_SECRET:
        return jsonify({"error": "Guest access not configured"}), 503
    refused = _turnstile_refusal()
    if refused is not None:
        return refused
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


USER_DAILY_LIMIT = parse("5 per day")
GLOBAL_DAILY_LIMIT = parse("70 per day")
GUEST_IP_DAILY_LIMIT = parse("10 per day")  # guests only
SIGNED_IN_IP_BACKSTOP = parse("200 per day")  # loose: signed-in users are capped per user

PREVIEW_GLOBAL_DAILY_DEFAULT = 20


def _preview_global_daily_limit():
    """PREVIEW_GLOBAL_DAILY_LIMIT as a limits item. A bad value logs and uses the default."""
    raw = os.getenv("PREVIEW_GLOBAL_DAILY_LIMIT", "").strip()
    if not raw:
        return parse(f"{PREVIEW_GLOBAL_DAILY_DEFAULT} per day")
    try:
        count = int(raw)
        if count < 1:
            raise ValueError("must be at least 1")
    except ValueError as e:
        logger.error(
            "PREVIEW_GLOBAL_DAILY_LIMIT=%r is invalid (%s); using %d",
            raw, e, PREVIEW_GLOBAL_DAILY_DEFAULT,
        )
        return parse(f"{PREVIEW_GLOBAL_DAILY_DEFAULT} per day")
    prod_cap = GLOBAL_DAILY_LIMIT.amount
    if count > prod_cap:
        logger.warning(
            "PREVIEW_GLOBAL_DAILY_LIMIT=%d exceeds the prod cap (%d); clamping to %d",
            count, prod_cap, prod_cap,
        )
        count = prod_cap
    return parse(f"{count} per day")


PREVIEW_GLOBAL_DAILY_LIMIT = _preview_global_daily_limit()

GUEST_SHARE_DEFAULT = 0.5


def _guest_daily_share() -> float:
    """GUEST_DAILY_SHARE as a fraction in (0, 1]. A bad value logs and uses the default."""
    raw = os.getenv("GUEST_DAILY_SHARE", "").strip()
    if not raw:
        return GUEST_SHARE_DEFAULT
    try:
        share = float(raw)
        if not 0 < share <= 1:
            raise ValueError("must be greater than 0 and at most 1")
    except ValueError as e:
        logger.error("GUEST_DAILY_SHARE=%r is invalid (%s); using %s", raw, e, GUEST_SHARE_DEFAULT)
        return GUEST_SHARE_DEFAULT
    return share


GUEST_DAILY_SHARE = _guest_daily_share()


def _guest_cap(global_limit):
    """Guests' combined daily ceiling on one global budget: GUEST_DAILY_SHARE of it, at least 1."""
    return parse(f"{max(1, math.floor(global_limit.amount * GUEST_DAILY_SHARE))} per day")


def _origin_class() -> str:
    """Classify the request's Origin as "preview" or "prod" for the global budget.

    "preview" needs a full match of PREVIEW_ORIGIN_REGEX and a different value from
    FRONTEND_ORIGIN. A missing, empty or invalid Origin counts as "prod".

    Tradeoff: Origin is client-controlled. A non-browser caller can send a preview
    Origin to charge the preview bucket instead of prod. That only moves its spend
    into the small preview cap. Worst-case total global spend per day is
    GLOBAL_DAILY_LIMIT (70) + PREVIEW_GLOBAL_DAILY_LIMIT (20 by default).
    """
    origin = request.headers.get("Origin", "")
    if not origin or origin == _frontend_origin:
        return "prod"
    if _preview_origin_pattern is not None and _preview_origin_pattern.match(origin):
        return "preview"
    return "prod"


def charge_quota():
    """Charge the daily budgets for an authenticated request, most specific first.

    Called from the view, after require_auth, so forged or garbage tokens are
    never charged. hit() is atomic in the storage backend, so parallel requests
    cannot all pass a check before any of them is counted. Each refusal stops the
    chain, so a request refused early never uses a later budget:
      1. per-IP daily: 10 for guests, 200 backstop for signed-in users
      2. per-user daily: 5 (guests share one bucket per IP)
      3. global daily: 70 for prod origins, or PREVIEW_GLOBAL_DAILY_LIMIT (20) in a
         separate bucket for preview origins (see _origin_class). Guests also pass
         a guest share of that budget first (GUEST_DAILY_SHARE, default 50%), so
         signed-in users always keep the rest.

    Returns a 429 response, or None to continue. Fails closed: a storage error is
    logged through flask-limiter's logger and returns 503, because the request
    cannot be charged against the budget.
    """
    if not limiter.enabled:
        return None
    try:
        ip = client_ip()
        is_guest = g.clerk_payload.get("role") == "guest"
        if is_guest:
            if not limiter.limiter.hit(GUEST_IP_DAILY_LIMIT, "ask-guest-ip", ip):
                return jsonify({"error": "IP daily limit reached"}), 429
        elif not limiter.limiter.hit(SIGNED_IN_IP_BACKSTOP, "ask-ip", ip):
            return jsonify({"error": "IP daily limit reached"}), 429
        if not limiter.limiter.hit(USER_DAILY_LIMIT, "ask-user", _user_key()):
            return jsonify({"error": "Daily limit reached"}), 429
        if _origin_class() == "preview":
            global_limit, bucket = PREVIEW_GLOBAL_DAILY_LIMIT, "preview"
        else:
            global_limit, bucket = GLOBAL_DAILY_LIMIT, "global"
        if is_guest and not limiter.limiter.hit(_guest_cap(global_limit), "ask-global-guest", bucket):
            return jsonify({"error": "Service limit reached"}), 429
        if not limiter.limiter.hit(global_limit, "ask-global", bucket):
            return jsonify({"error": "Service limit reached"}), 429
    except Exception:
        logging.getLogger("flask-limiter").exception("Failed to charge rate limit. Refusing the request")
        return jsonify({"error": "Rate limit service unavailable"}), 503
    return None


# The per-minute per-IP limit is a decorator above require_auth, so it runs before the
# token is checked and unauthenticated floods count against it. Every other budget is
# charged in the view by charge_quota(), after auth.
@app.route("/ask", methods=["POST"])
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
    # Logged for every authenticated /ask. Never the question text or the token.
    payload = g.clerk_payload
    kind = "guest" if payload.get("role") == "guest" else "clerk"
    logger.info("ask ip=%s kind=%s sub=%s", client_ip(), kind, _sub_fingerprint(payload.get("sub")))

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

    # Charged only once the request is valid, so malformed requests do not use quota.
    refused = charge_quota()
    if refused is not None:
        return refused

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
