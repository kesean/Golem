# Testing Design — Dev Support AI Chatbot

**Date:** 2026-03-27
**Scope:** Unit + integration tests for backend (Flask) and frontend (Vite/Vanilla JS)
**Goal:** Regression safety, portfolio quality, and CI gate before production deployment

---

## 1. Architecture

```
dev-support-chatbot/
├── tests/                        ← backend test suite
│   ├── __init__.py
│   ├── conftest.py               ← Flask app fixture, shared mocks, JWT helper
│   ├── test_prompt.py            ← build_messages() unit tests
│   ├── test_auth.py              ← require_auth decorator tests
│   └── test_routes.py            ← /ask/stream route integration tests
│
├── frontend/
│   ├── vite.config.js            ← created; adds Vitest config block
│   └── tests/
│       ├── setup.js              ← jsdom stubs (clipboard, Convex, Clerk globals)
│       ├── app.test.js           ← XML parsing, history mgmt, UI logic
│       └── prompt.test.js        ← pure frontend utility logic (if any)
│
└── .github/
    └── workflows/
        └── test.yml              ← CI: backend + frontend jobs run in parallel on push/PR to main
```

**Out of scope:**
- `frontend/src/main.js` — pure third-party wiring (Clerk + Convex), no testable logic
- `askQuestion()` streaming fetch — too many external dependencies; belongs to E2E if added later
- Rate limiter behavior — disabled in test config to avoid interference

---

## 2. Backend Tests

**New dependencies** (added to `requirements.txt`): `pytest`, `pytest-flask`

### `conftest.py`
- `app` fixture: creates Flask test client with `TESTING=True` and rate limiter disabled
- `valid_jwt` fixture: generates a signed JWT using a test RSA key pair
- `mock_jwks` fixture: patches `app._fetch_jwks` to return the matching public key in JWKS format

### `test_prompt.py` — pure unit tests, no mocks
| Test | Expected |
|------|----------|
| `build_messages(question)` with no history | `[{role: user, content: question}]` |
| `build_messages(question, history=[...])` | history prepended, question appended |
| `build_messages(question, history=None)` | same as no-history case, no error |

### `test_auth.py` — `require_auth` decorator
| Test | Expected |
|------|----------|
| No `Authorization` header | 401 |
| Malformed token (not a JWT) | 401 |
| Expired token | 401 |
| JWKS fetch raises exception | 401 |
| Valid signed token | request passes through to route |

### `test_routes.py` — `/ask/stream` integration
| Test | Expected |
|------|----------|
| Non-JSON `Content-Type` | 415 |
| Question exceeds 2000 chars | 400 |
| Empty / missing `question` field | 400 |
| Valid request | 200, SSE stream with expected chunks |
| `history` array in body | forwarded to `build_messages` |

**Mocking strategy:**
- `unittest.mock.patch('app._fetch_jwks')` → returns fake JWKS with test public key
- `unittest.mock.patch('app.client.messages.stream')` → returns fake streaming context manager yielding test chunks

---

## 3. Frontend Tests

**New dependencies** (added to `frontend/package.json` devDependencies): `vitest`, `@vitest/coverage-v8`, `jsdom`

**Vitest config** in `vite.config.js`:
```js
test: {
  environment: 'jsdom',
  setupFiles: ['./tests/setup.js'],
  include: ['tests/**/*.test.js'],
}
```

### `tests/setup.js`
Stubs out globals that `app.js` references but aren't available in jsdom:
- `navigator.clipboard.writeText` → `vi.fn()`
- `window.history.replaceState` → `vi.fn()`
- Convex/Clerk globals → stubbed as empty objects

### `app.test.js`

**XML parsing:**
| Test | Expected |
|------|----------|
| Valid `<response>` XML | extracts summary, root_cause, debug_steps, docs correctly |
| Missing optional `<docs>` | no error; docs section empty |
| Malformed XML | graceful fallback; error shown, no crash |

**Conversation history management:**
| Test | Expected |
|------|----------|
| After 2 turns | `_conversationHistory` has 4 messages |
| After 11 turns (22 messages) | history capped at 20; oldest 2 dropped |
| `newConversation()` | resets history to `[]`, clears `activeHistoryId` |

**`renderResponse()` DOM output:**
| Test | Expected |
|------|----------|
| Valid XML input | `#summary` populated with expected text |
| After render | `#response-area` has `.sections-ready` class |
| No product tag in XML | `#product-tag-badge` has `.hidden` class |

**`shareResponse()` / `copyResponse()`:**
| Test | Expected |
|------|----------|
| `copyResponse()` called | `navigator.clipboard.writeText` called with response text |
| `shareResponse()` with active history ID | clipboard called with URL containing share param |
| Button label after copy | temporarily changes to "Copied!" / "Copied link!" |

---

## 4. CI Workflow

**File:** `.github/workflows/test.yml`
**Triggers:** push or PR targeting `main`

```yaml
jobs:
  backend:
    runs-on: ubuntu-latest
    env:
      ANTHROPIC_API_KEY: test-key-placeholder
      CLERK_JWKS_URL: https://placeholder.clerk.accounts.dev/.well-known/jwks.json
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt pytest pytest-flask
      - run: pytest tests/ -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
        working-directory: frontend
      - run: npx vitest run
        working-directory: frontend
```

Both jobs run in parallel. A PR cannot merge if either job fails (enforced via branch protection on `main`).

**Secret handling:** `ANTHROPIC_API_KEY` and `CLERK_JWKS_URL` are set to non-empty placeholder strings in the workflow env — no real secrets needed since all external calls are mocked.
