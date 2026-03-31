# Streaming to JSON Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the streaming `/ask/stream` endpoint with a standard synchronous `/ask` endpoint that returns a JSON response, and update the frontend to consume it.

**Architecture:** The backend calls `client.messages.create()` instead of `client.messages.stream()`, returns `jsonify({ "response": xml_text })`, and the frontend reads it with `res.json()`. No change to auth, rate limiting, XML parsing, Convex history, or error handling.

**Tech Stack:** Python 3 / Flask / Anthropic SDK / Vanilla JS / Vitest / pytest

---

## File Map

| File | Change |
|------|--------|
| `app.py` | Rename route, replace streaming with `messages.create`, update imports |
| `frontend/src/app.js` | Update fetch URL, replace stream reader with `res.json()` |
| `tests/test_routes.py` | Update route paths, remove `_FakeStreamCtx`, mock `messages.create` instead |

---

### Task 1: Update backend tests for the new `/ask` JSON endpoint

**Files:**
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests for the new `/ask` route**

Replace the entire contents of `tests/test_routes.py` with:

```python
"""test_routes.py — Integration tests for the /ask route."""

from unittest.mock import MagicMock, patch


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_message(text):
    """Return a mock object matching the shape of anthropic.types.Message."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ── Input validation ──────────────────────────────────────────────────────────

def test_non_json_content_type_returns_415(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        content_type="text/plain",
        data="hello",
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 415


def test_missing_question_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": ""},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


def test_question_over_2000_chars_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": "x" * 2001},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400
    assert b"2000" in resp.data


def test_invalid_history_format_returns_400(client, mock_jwks, valid_token):
    resp = client.post(
        "/ask",
        json={"question": "test?", "history": "not-a-list"},
        headers=_auth_headers(valid_token),
    )
    assert resp.status_code == 400


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_request_returns_json_response(client, mock_jwks, valid_token):
    xml = "<product_tag>Authentication</product_tag><summary>Test</summary>"
    with patch("app.client.messages.create", return_value=_fake_message(xml)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    data = resp.get_json()
    assert "response" in data
    assert "Authentication" in data["response"]
    assert "Test" in data["response"]


def test_history_is_forwarded_to_anthropic(client, mock_jwks, valid_token):
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    xml = "<product_tag>Other</product_tag><summary>ok</summary>"
    with patch("app.client.messages.create", return_value=_fake_message(xml)) as mock_create:
        client.post(
            "/ask",
            json={"question": "Follow-up?", "history": history},
            headers=_auth_headers(valid_token),
        )
    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "Previous question"}
    assert messages[-1] == {"role": "user", "content": "Follow-up?"}
```

- [ ] **Step 2: Run tests to confirm they fail (route doesn't exist yet)**

```bash
cd /Users/kesean/Developer/dev-support-chatbot
python -m pytest tests/test_routes.py -v
```

Expected: All tests FAIL with `404` or `AssertionError` — the `/ask` route doesn't exist yet and the mock targets `messages.create` which isn't wired up.

---

### Task 2: Update the Flask backend

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace the streaming route with a standard JSON endpoint**

Replace the entire contents of `app.py` with:

```python
"""
app.py — Flask app and API routes.
"""

import os
import json
import time
import logging
import urllib.request
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from anthropic import Anthropic
from dotenv import load_dotenv
import jwt
from prompt import SYSTEM_PROMPT, build_messages

load_dotenv()

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=[])
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


@app.route("/ask", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
def ask():
    """
    Accepts a JSON body: { "question": "...", "history": [...] }
    Returns a JSON response: { "response": "<xml>..." }
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

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=build_messages(question, history),
    )

    return jsonify({"response": message.content[0].text})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
```

- [ ] **Step 2: Run tests to confirm they now pass**

```bash
cd /Users/kesean/Developer/dev-support-chatbot
python -m pytest tests/test_routes.py -v
```

Expected output:
```
tests/test_routes.py::test_non_json_content_type_returns_415 PASSED
tests/test_routes.py::test_missing_question_returns_400 PASSED
tests/test_routes.py::test_question_over_2000_chars_returns_400 PASSED
tests/test_routes.py::test_invalid_history_format_returns_400 PASSED
tests/test_routes.py::test_valid_request_returns_json_response PASSED
tests/test_routes.py::test_history_is_forwarded_to_anthropic PASSED
```

- [ ] **Step 3: Run the full test suite to confirm nothing else broke**

```bash
cd /Users/kesean/Developer/dev-support-chatbot
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add app.py tests/test_routes.py
git commit -m "refactor: replace streaming endpoint with standard JSON /ask route"
```

---

### Task 3: Update the frontend fetch call

**Files:**
- Modify: `frontend/src/app.js:263-282`

- [ ] **Step 1: Replace the stream reader with a simple JSON fetch**

In `frontend/src/app.js`, replace lines 263–282 (the fetch call and stream reader loop) with:

```js
    const res = await fetch('/ask', {
      method: 'POST',
      headers,
      body: JSON.stringify({ question, history: _conversationHistory }),
    })

    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.error || 'Something went wrong.')
    }

    const { response } = await res.json()
```

Then on line 285, the existing `renderResponse(accumulated)` call becomes `renderResponse(response)`.

And on lines 289–292, `accumulated` becomes `response`:

```js
    _conversationHistory.push({ role: 'user', content: question })
    _conversationHistory.push({ role: 'assistant', content: response })
    if (_conversationHistory.length > 20) _conversationHistory.splice(0, 2)

    activeHistoryId = await saveToHistory(question, response)
```

The full updated block (lines 256–303) should look like:

```js
  try {
    const headers = { 'Content-Type': 'application/json' }
    if (_getToken) {
      const token = await _getToken()
      if (token) headers['Authorization'] = `Bearer ${token}`
    }

    const res = await fetch('/ask', {
      method: 'POST',
      headers,
      body: JSON.stringify({ question, history: _conversationHistory }),
    })

    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.error || 'Something went wrong.')
    }

    const { response } = await res.json()

    skeleton.classList.add('hidden')
    renderResponse(response)

    // Append to in-memory conversation (cap at 10 turns = 20 messages)
    _conversationHistory.push({ role: 'user', content: question })
    _conversationHistory.push({ role: 'assistant', content: response })
    if (_conversationHistory.length > 20) _conversationHistory.splice(0, 2)

    activeHistoryId = await saveToHistory(question, response)
    renderHistorySidebar()

  } catch (err) {
    skeleton.classList.add('hidden')
    errorMsg.textContent = err.message
    errorArea.classList.remove('hidden')
  } finally {
    btn.disabled = false
    btn.textContent = 'Ask'
  }
```

- [ ] **Step 2: Run the frontend tests**

```bash
cd /Users/kesean/Developer/dev-support-chatbot/frontend
npm test
```

Expected: All tests pass.

- [ ] **Step 3: Smoke test manually**

Start both servers:
```bash
# Terminal 1
cd /Users/kesean/Developer/dev-support-chatbot && python app.py

# Terminal 2
cd /Users/kesean/Developer/dev-support-chatbot/frontend && npm run dev
```

Open `http://localhost:5173`, sign in, ask a question. Verify:
- Loading skeleton appears
- Full structured response renders (product tag, summary, root cause, debug steps, docs)
- No errors in browser console

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.js
git commit -m "refactor: update frontend to consume /ask JSON endpoint"
```

---

### Task 4: Update the docstring in app.py

**Files:**
- Modify: `app.py`

This is already done as part of Task 2 — the new `ask()` function has the correct docstring. No additional action needed.

---

### Task 5: Final verification and push

- [ ] **Step 1: Run the full backend test suite one last time**

```bash
cd /Users/kesean/Developer/dev-support-chatbot
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Push the branch**

```bash
git push
```
