# V2a Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add token/latency logging to every `/ask` request, store eval records in Convex, and surface thumbs up/down feedback buttons on each response card.

**Architecture:** Flask captures `input_tokens`, `output_tokens`, and `latency_ms` from the Anthropic SDK response and returns them in the JSON response. The frontend writes a Convex `evals` record after each response, stores the record ID on the response card, and calls a `setFeedback` mutation when the user clicks thumbs up/down.

**Tech Stack:** Flask · Anthropic SDK · Convex (TypeScript mutations) · Vanilla JS · Playwright · convex-test · vitest

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `app.py` | Add timing + token capture to `/ask` response |
| Modify | `tests/test_routes.py` | Add test for new response fields |
| Modify | `frontend/convex/schema.ts` | Add `evals` table |
| Modify | `frontend/vite.config.js` | Add convex test glob + edge-runtime env |
| Create | `frontend/convex/evals.ts` | `createEval` and `setFeedback` mutations |
| Create | `frontend/convex/evals.test.ts` | convex-test unit tests for both mutations |
| Modify | `frontend/index.html` | Add thumb up/down buttons to `.response-actions` |
| Modify | `frontend/src/style.css` | Add `.feedback-btn` styles and state variants |
| Modify | `frontend/src/app.js` | Eval creation, feedback button wiring, `thumbFeedback` |
| Modify | `frontend/tests/app.test.js` | Update API mock + DOM fixture; add thumbFeedback tests |
| Modify | `frontend/src/main.js` | Expose `thumbFeedback` on window; add test-mode bypass |
| Create | `frontend/playwright.config.ts` | Playwright config pointing at Vite dev server |
| Create | `frontend/e2e/feedback.spec.ts` | E2E tests for button state, toggle, switching |

---

### Task 1: Flask — Capture and return token usage + latency

**Files:**
- Modify: `tests/test_routes.py`
- Modify: `app.py:148-157`

- [ ] **Step 1: Update `_fake_message` to mock `usage`**

In `tests/test_routes.py`, replace the existing `_fake_message` function:

```python
def _fake_message(text, input_tokens=10, output_tokens=20):
    """Return a mock object matching the shape of anthropic.types.Message."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg
```

- [ ] **Step 2: Write the failing test for new response fields**

Append to `tests/test_routes.py`:

```python
def test_response_includes_token_usage_and_latency(client, mock_jwks, valid_token):
    xml = "<product_tag>Authentication</product_tag><summary>Test</summary>"
    with patch("app.client.messages.create", return_value=_fake_message(xml, input_tokens=50, output_tokens=100)):
        resp = client.post(
            "/ask",
            json={"question": "Why am I getting a 401?"},
            headers=_auth_headers(valid_token),
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["input_tokens"] == 50
    assert data["output_tokens"] == 100
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] >= 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_routes.py::test_response_includes_token_usage_and_latency -v
```

Expected: `FAILED` — `KeyError: 'input_tokens'`

- [ ] **Step 4: Update `app.py` — add timing and token metrics**

In `app.py`, replace the block starting at `message = client.messages.create(...)` through `return jsonify(...)`:

```python
    start = time.time()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=build_messages(question, history),
    )
    latency_ms = round((time.time() - start) * 1000)

    if not message.content:
        return jsonify({"error": "No response from model"}), 502
    return jsonify({
        "response": message.content[0].text,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "latency_ms": latency_ms,
    })
```

- [ ] **Step 5: Run all backend tests to verify they pass**

```bash
pytest tests/ -v
```

Expected: All tests pass. The existing `test_valid_request_returns_json_response` still passes because it only asserts `"response" in data`.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_routes.py
git commit -m "feat: return token usage and latency from /ask (US-V2a-1)"
```

---

### Task 2: Convex schema — Add `evals` table

**Files:**
- Modify: `frontend/convex/schema.ts`
- Modify: `frontend/vite.config.js`

- [ ] **Step 1: Update `frontend/convex/schema.ts`**

Replace the full file contents:

```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  history: defineTable({
    userId: v.string(),
    question: v.string(),
    rawXml: v.string(),
  }).index("by_user", ["userId"]),
  evals: defineTable({
    userId: v.string(),
    question: v.string(),
    response: v.string(),
    latency_ms: v.number(),
    input_tokens: v.number(),
    output_tokens: v.number(),
    feedback: v.optional(v.union(v.literal("up"), v.literal("down"))),
  }).index("by_user", ["userId"]),
});
```

- [ ] **Step 2: Install convex-test and edge-runtime**

```bash
cd frontend && npm install --save-dev convex-test @edge-runtime/vm
```

Expected output: `convex-test` and `@edge-runtime/vm` added to `devDependencies` in `package.json`.

- [ ] **Step 3: Update `frontend/vite.config.js` to include Convex test files**

Replace the `test` block in `frontend/vite.config.js`:

```javascript
import { defineConfig } from 'vite'

export default defineConfig({
  // Load .env from the project root (one level up from frontend/)
  envDir: '../',
  server: {
    proxy: {
      // Forward all /ask/* requests to the Flask API during development
      '/ask': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
  test: {
    environmentMatchGlobs: [
      ['convex/**/*.test.ts', 'edge-runtime'],
      ['tests/**/*.test.js', 'jsdom'],
    ],
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.test.js', 'convex/**/*.test.ts'],
  },
})
```

- [ ] **Step 4: Commit**

```bash
git add frontend/convex/schema.ts frontend/vite.config.js frontend/package.json frontend/package-lock.json
git commit -m "feat: add evals table to Convex schema (US-V2a-2)"
```

---

### Task 3: Convex evals mutations (TDD)

**Files:**
- Create: `frontend/convex/evals.test.ts`
- Create: `frontend/convex/evals.ts`

- [ ] **Step 1: Create failing tests in `frontend/convex/evals.test.ts`**

```typescript
/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

// ── createEval ────────────────────────────────────────────────────────────────

test("createEval inserts a record and returns its id", async () => {
  const t = convexTest(schema, modules);
  const evalId = await t
    .withIdentity({ tokenIdentifier: "test|user1" })
    .mutation(api.evals.createEval, {
      question: "Why am I getting a 401?",
      response: "<summary>Test</summary>",
      latency_ms: 500,
      input_tokens: 100,
      output_tokens: 200,
    });
  expect(typeof evalId).toBe("string");
  expect(evalId.length).toBeGreaterThan(0);
});

test("createEval throws when unauthenticated", async () => {
  const t = convexTest(schema, modules);
  await expect(
    t.mutation(api.evals.createEval, {
      question: "Why?",
      response: "<summary>Test</summary>",
      latency_ms: 100,
      input_tokens: 10,
      output_tokens: 20,
    })
  ).rejects.toThrow("Unauthenticated");
});

// ── setFeedback ───────────────────────────────────────────────────────────────

test("setFeedback patches feedback to 'up'", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, {
    evalId,
    feedback: "up",
  });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBe("up");
});

test("setFeedback switches feedback from 'up' to 'down'", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "up" });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "down" });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBe("down");
});

test("setFeedback clears feedback when passed undefined", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "up" });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: undefined });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBeUndefined();
});

test("setFeedback throws for a record owned by another user", async () => {
  const t = convexTest(schema, modules);
  const id1 = { tokenIdentifier: "test|user1" };
  const id2 = { tokenIdentifier: "test|user2" };
  const evalId = await t.withIdentity(id1).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await expect(
    t.withIdentity(id2).mutation(api.evals.setFeedback, { evalId, feedback: "up" })
  ).rejects.toThrow("Not found");
});
```

- [ ] **Step 2: Run tests to verify they all fail**

```bash
cd frontend && npm test
```

Expected: 7 failing tests — `api.evals is undefined` or similar.

- [ ] **Step 3: Create `frontend/convex/evals.ts`**

```typescript
import { mutation } from "./_generated/server";
import { v } from "convex/values";

export const createEval = mutation({
  args: {
    question: v.string(),
    response: v.string(),
    latency_ms: v.number(),
    input_tokens: v.number(),
    output_tokens: v.number(),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    return await ctx.db.insert("evals", {
      userId: identity.tokenIdentifier,
      question: args.question,
      response: args.response,
      latency_ms: args.latency_ms,
      input_tokens: args.input_tokens,
      output_tokens: args.output_tokens,
    });
  },
});

export const setFeedback = mutation({
  args: {
    evalId: v.id("evals"),
    feedback: v.optional(v.union(v.literal("up"), v.literal("down"))),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    const record = await ctx.db.get(args.evalId);
    if (!record || record.userId !== identity.tokenIdentifier) {
      throw new Error("Not found");
    }
    await ctx.db.patch(args.evalId, { feedback: args.feedback });
  },
});
```

- [ ] **Step 4: Run tests to verify they all pass**

```bash
cd frontend && npm test
```

Expected: all 7 Convex tests pass. Existing `tests/app.test.js` tests also still pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/convex/evals.ts frontend/convex/evals.test.ts
git commit -m "feat: add createEval and setFeedback Convex mutations (US-V2a-3)"
```

---

### Task 4: HTML thumb buttons + CSS styles

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Add thumb buttons to `frontend/index.html`**

Find the `.response-actions` div (lines 91–95) and replace it:

```html
              <div class="response-actions">
                <button id="share-btn" class="copy-btn" onclick="shareResponse()">Share</button>
                <button id="copy-btn" class="copy-btn" onclick="copyResponse()">Copy</button>
                <button id="thumb-up-btn" class="feedback-btn" onclick="thumbFeedback('up')" disabled aria-label="Helpful">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
                    <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                  </svg>
                </button>
                <button id="thumb-down-btn" class="feedback-btn" onclick="thumbFeedback('down')" disabled aria-label="Not helpful">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
                    <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
                  </svg>
                </button>
              </div>
```

- [ ] **Step 2: Add `.feedback-btn` styles to `frontend/src/style.css`**

Append after the `/* ── Spinner ──` block (before `/* ── Responsive ──`):

```css
/* ── Feedback buttons ────────────────────────────────────────────────────────── */

.feedback-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.feedback-btn:hover:not(:disabled) {
  color: var(--teal);
  border-color: rgba(89,201,165,0.4);
  background: rgba(89,201,165,0.07);
}

.feedback-btn.active-up {
  color: var(--teal);
  border-color: rgba(89,201,165,0.4);
  background: rgba(89,201,165,0.15);
}

.feedback-btn.active-down {
  color: var(--coral);
  border-color: rgba(239,111,108,0.28);
  background: rgba(239,111,108,0.13);
}

.feedback-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html frontend/src/style.css
git commit -m "feat: add thumb feedback buttons to response card (US-V2a-4)"
```

---

### Task 5: app.js eval integration + vitest updates

**Files:**
- Modify: `frontend/src/app.js`
- Modify: `frontend/tests/app.test.js`
- Modify: `frontend/src/main.js`

- [ ] **Step 1: Update the Convex API mock in `frontend/tests/app.test.js`**

Replace the `vi.mock(...)` block at the top of the file:

```javascript
vi.mock('../convex/_generated/api.js', () => ({
  api: {
    history: {
      list: 'history:list',
      add: 'history:add',
      clear: 'history:clear',
      getById: 'history:getById',
    },
    evals: {
      createEval: 'evals:createEval',
      setFeedback: 'evals:setFeedback',
    },
  },
}))
```

- [ ] **Step 2: Add thumb buttons and `thumbFeedback` import to the test file**

Update the import line to include `thumbFeedback` and `initApp`:

```javascript
import {
  extractSection,
  renderResponse,
  newConversation,
  copyResponse,
  shareResponse,
  thumbFeedback,
  initApp,
} from '../src/app.js'
```

Update `DOM_HTML` to include the thumb buttons (so `newConversation` calls to `_disableFeedback` don't hit missing elements):

```javascript
const DOM_HTML = `
  <span   id="product-tag-badge" class="hidden"></span>
  <div    id="summary"></div>
  <div    id="root-cause"></div>
  <ol     id="debug-steps"></ol>
  <div    id="docs-section" class="hidden">
    <ul   id="docs"></ul>
  </div>
  <div    id="response-area" class="hidden"></div>
  <div    id="error-area"    class="hidden"></div>
  <button id="share-btn">Share</button>
  <button id="copy-btn">Copy</button>
  <button id="thumb-up-btn" class="feedback-btn" disabled></button>
  <button id="thumb-down-btn" class="feedback-btn" disabled></button>
  <textarea id="question"></textarea>
  <ul     id="history-list"></ul>
`
```

- [ ] **Step 3: Write failing tests for `thumbFeedback`**

Append to `frontend/tests/app.test.js`:

```javascript
// ── thumbFeedback ─────────────────────────────────────────────────────────────

const SAMPLE_XML_FULL = `<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test cause.</root_cause><debug_steps>Step 1: Check logs.</debug_steps><docs></docs>`

describe('thumbFeedback', () => {
  let mockConvex

  beforeEach(async () => {
    document.body.innerHTML = DOM_HTML
    mockConvex = {
      query: vi.fn().mockResolvedValue([]),
      mutation: vi.fn()
        .mockResolvedValueOnce('hist-id')  // history.add
        .mockResolvedValueOnce('eval-id'), // evals.createEval
      setAuth: vi.fn(),
    }
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        response: SAMPLE_XML_FULL,
        input_tokens: 50,
        output_tokens: 100,
        latency_ms: 500,
      }),
    })
    await initApp({ convex: mockConvex, getToken: async () => 'token' })
    document.getElementById('question').value = 'test question'
    await askQuestion()
    // Reset mutation mock for setFeedback calls
    mockConvex.mutation.mockResolvedValue(undefined)
  })

  it('enables thumb buttons after a response is received', () => {
    expect(document.getElementById('thumb-up-btn').disabled).toBe(false)
    expect(document.getElementById('thumb-down-btn').disabled).toBe(false)
  })

  it('adds active-up class when thumbFeedback("up") is called', async () => {
    await thumbFeedback('up')
    expect(document.getElementById('thumb-up-btn').classList.contains('active-up')).toBe(true)
    expect(document.getElementById('thumb-down-btn').classList.contains('active-down')).toBe(false)
  })

  it('removes active-up class when thumbFeedback("up") is called again (toggle off)', async () => {
    await thumbFeedback('up')
    await thumbFeedback('up')
    expect(document.getElementById('thumb-up-btn').classList.contains('active-up')).toBe(false)
  })

  it('switches to active-down and clears active-up when thumbFeedback("down") after "up"', async () => {
    await thumbFeedback('up')
    await thumbFeedback('down')
    expect(document.getElementById('thumb-down-btn').classList.contains('active-down')).toBe(true)
    expect(document.getElementById('thumb-up-btn').classList.contains('active-up')).toBe(false)
  })

  it('calls setFeedback mutation with correct evalId and feedback', async () => {
    await thumbFeedback('up')
    expect(mockConvex.mutation).toHaveBeenCalledWith('evals:setFeedback', {
      evalId: 'eval-id',
      feedback: 'up',
    })
  })

  it('disables thumb buttons and clears active state after newConversation', async () => {
    await thumbFeedback('up')
    newConversation()
    expect(document.getElementById('thumb-up-btn').disabled).toBe(true)
    expect(document.getElementById('thumb-up-btn').classList.contains('active-up')).toBe(false)
  })
})
```

Also add `askQuestion` to the import line:

```javascript
import {
  extractSection,
  renderResponse,
  newConversation,
  copyResponse,
  shareResponse,
  thumbFeedback,
  askQuestion,
  initApp,
} from '../src/app.js'
```

- [ ] **Step 4: Run tests to confirm they fail**

```bash
cd frontend && npm test -- tests/app.test.js
```

Expected: `thumbFeedback is not a function` or similar — the new exports and logic don't exist yet.

- [ ] **Step 5: Update `frontend/src/app.js`**

**5a.** Add `_currentEvalId` to the module state section (after `let _conversationHistory = []`):

```javascript
let _currentEvalId = null
```

**5b.** Add three helper functions after the `// ─── History (Convex) ───` section:

```javascript
// ─── Feedback helpers ─────────────────────────────────────────────────────────

function _resetFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.classList.remove('active-up')
  down.classList.remove('active-down')
}

function _enableFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.disabled   = false
  down.disabled = false
}

function _disableFeedback() {
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return
  up.disabled   = true
  down.disabled = true
}
```

**5c.** Add the exported `thumbFeedback` function before the `// ─── Main ask handler ───` comment:

```javascript
export async function thumbFeedback(type) {
  if (!_currentEvalId || !_convex) return
  const up   = document.getElementById('thumb-up-btn')
  const down = document.getElementById('thumb-down-btn')
  if (!up || !down) return

  const isAlreadyActive =
    (type === 'up'   && up.classList.contains('active-up')) ||
    (type === 'down' && down.classList.contains('active-down'))

  _resetFeedback()
  const newFeedback = isAlreadyActive ? undefined : type
  if (newFeedback === 'up')   up.classList.add('active-up')
  if (newFeedback === 'down') down.classList.add('active-down')

  await _convex.mutation(api.evals.setFeedback, {
    evalId: _currentEvalId,
    feedback: newFeedback,
  })
}
```

**5d.** In `askQuestion()`, replace:

```javascript
    const { response } = await res.json()
```

with:

```javascript
    const { response, input_tokens, output_tokens, latency_ms } = await res.json()
```

**5e.** In `askQuestion()`, after `activeHistoryId = await saveToHistory(question, response)`, add:

```javascript
    _currentEvalId = await _convex.mutation(api.evals.createEval, {
      question,
      response,
      latency_ms,
      input_tokens,
      output_tokens,
    })
    _resetFeedback()
    _enableFeedback()
```

**5f.** In `newConversation()`, after `activeHistoryId = null`, add:

```javascript
  _currentEvalId = null
  _resetFeedback()
  _disableFeedback()
```

**5g.** In `loadHistoryEntry()`, after `_conversationHistory = []`, add:

```javascript
  _currentEvalId = null
  _resetFeedback()
  _disableFeedback()
```

- [ ] **Step 6: Update `frontend/src/main.js` — expose `thumbFeedback` on window**

Add `thumbFeedback` to the import line:

```javascript
import { askQuestion, clearHistory, newConversation, copyResponse, shareResponse, thumbFeedback, initApp } from './app.js'
```

In `showApp()`, after `window.shareResponse = shareResponse`, add:

```javascript
  window.thumbFeedback = thumbFeedback
```

- [ ] **Step 7: Run all frontend tests to verify they pass**

```bash
cd frontend && npm test
```

Expected: all tests pass, including the new `thumbFeedback` describe block.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app.js frontend/src/main.js frontend/tests/app.test.js
git commit -m "feat: wire eval creation and thumbs feedback in app.js (US-V2a-5)"
```

---

### Task 6: Playwright setup + auth bypass

**Files:**
- Modify: `frontend/src/main.js`
- Create: `frontend/playwright.config.ts`

- [ ] **Step 1: Install Playwright**

```bash
cd frontend && npm install --save-dev @playwright/test && npx playwright install chromium
```

Expected: Playwright installed, Chromium browser downloaded.

- [ ] **Step 2: Restructure `frontend/src/main.js` to support test-mode bypass**

Replace the full file contents:

```javascript
import { ConvexClient } from 'convex/browser'
import './style.css'
import { askQuestion, clearHistory, newConversation, copyResponse, shareResponse, thumbFeedback, initApp } from './app.js'

const authWall = document.getElementById('auth-wall')

if (import.meta.env.VITE_TEST_BYPASS_AUTH === 'true') {
  // Test mode: skip Clerk entirely, show app with a mock Convex client.
  // Only active when VITE_TEST_BYPASS_AUTH=true — never in production.
  const mockConvex = {
    query:    async () => [],
    mutation: async () => 'mock-id',
    setAuth:  () => {},
  }

  window.askQuestion    = askQuestion
  window.clearHistory   = clearHistory
  window.newConversation = newConversation
  window.copyResponse   = copyResponse
  window.shareResponse  = shareResponse
  window.thumbFeedback  = thumbFeedback

  document.getElementById('sign-out-btn').addEventListener('click', () => {})

  await initApp({ convex: mockConvex, getToken: async () => 'mock-token' })

  authWall.style.display = 'none'
  document.getElementById('app-root').style.display = ''
  document.body.style.visibility = 'visible'
} else {
  // Production mode: require Clerk auth.
  const { Clerk } = await import('@clerk/clerk-js')
  const clerk = new Clerk(import.meta.env.VITE_CLERK_PUBLISHABLE_KEY)
  await clerk.load()

  async function showApp() {
    const convex = new ConvexClient(import.meta.env.VITE_CONVEX_URL)

    convex.setAuth(async ({ forceRefreshToken }) => {
      return await clerk.session?.getToken({ template: 'convex' }) ?? null
    })

    window.askQuestion    = askQuestion
    window.clearHistory   = clearHistory
    window.newConversation = newConversation
    window.copyResponse   = copyResponse
    window.shareResponse  = shareResponse
    window.thumbFeedback  = thumbFeedback

    document.getElementById('sign-out-btn').addEventListener('click', async () => {
      await clerk.signOut()
      window.location.reload()
    })

    await initApp({
      convex,
      getToken: () => clerk.session?.getToken(),
    })

    authWall.style.display = 'none'
    document.getElementById('app-root').style.display = ''
    document.body.style.visibility = 'visible'
  }

  if (clerk.user) {
    await showApp()
  } else {
    await clerk.redirectToSignIn({ redirectUrl: window.location.href })
  }
}
```

- [ ] **Step 3: Create `frontend/playwright.config.ts`**

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://localhost:5173',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    env: {
      VITE_TEST_BYPASS_AUTH: 'true',
    },
  },
});
```

- [ ] **Step 4: Add a `test:e2e` script to `frontend/package.json`**

In `"scripts"`, add:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.js frontend/playwright.config.ts frontend/package.json
git commit -m "feat: add Playwright config and auth bypass for E2E tests (US-V2a-6)"
```

---

### Task 7: Playwright E2E tests

**Files:**
- Create: `frontend/e2e/feedback.spec.ts`

- [ ] **Step 1: Create `frontend/e2e/` directory and test file**

```bash
mkdir -p frontend/e2e
```

Create `frontend/e2e/feedback.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

const MOCK_RESPONSE = {
  response: '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>',
  input_tokens: 50,
  output_tokens: 100,
  latency_ms: 500,
};

test.beforeEach(async ({ page }) => {
  // Mock the /ask endpoint so no real Flask server is needed
  await page.route('**/ask', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_RESPONSE),
    });
  });
});

test('thumb buttons are disabled before any response is received', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#thumb-up-btn')).toBeDisabled();
  await expect(page.locator('#thumb-down-btn')).toBeDisabled();
});

test('thumb buttons are enabled after a response renders', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).not.toHaveClass(/hidden/);
  await expect(page.locator('#thumb-up-btn')).not.toBeDisabled();
  await expect(page.locator('#thumb-down-btn')).not.toBeDisabled();
});

test('clicking thumb-up activates it', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).not.toHaveClass(/hidden/);

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);
  await expect(page.locator('#thumb-down-btn')).not.toHaveClass(/active-down/);
});

test('clicking active thumb-up again deactivates it (toggle off)', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).not.toHaveClass(/hidden/);

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);
  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).not.toHaveClass(/active-up/);
});

test('clicking thumb-down after thumb-up switches selection', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).not.toHaveClass(/hidden/);

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);

  await page.locator('#thumb-down-btn').click();
  await expect(page.locator('#thumb-down-btn')).toHaveClass(/active-down/);
  await expect(page.locator('#thumb-up-btn')).not.toHaveClass(/active-up/);
});

test('thumb buttons reset to disabled after New Conversation', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).not.toHaveClass(/hidden/);
  await page.locator('#thumb-up-btn').click();

  // Click "New conversation" button
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#thumb-up-btn')).toBeDisabled();
  await expect(page.locator('#thumb-up-btn')).not.toHaveClass(/active-up/);
});
```

- [ ] **Step 2: Run Playwright tests**

```bash
cd frontend && npm run test:e2e
```

Expected: all 6 E2E tests pass. If the Vite dev server isn't already running, Playwright starts it automatically.

- [ ] **Step 3: Run unit tests one final time to confirm nothing broke**

```bash
cd frontend && npm test
```

Expected: all Vitest tests (app.test.js + evals.test.ts) pass.

- [ ] **Step 4: Run backend tests**

```bash
pytest tests/ -v
```

Expected: all pytest tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/feedback.spec.ts
git commit -m "test: add Playwright E2E tests for feedback buttons (US-V2a-7)"
```

---

## Deployment checklist

After all tasks pass locally:

1. Push branch → Railway auto-deploys the Flask backend (no config changes needed — only JSON response shape changed).
2. Push branch → Vercel auto-deploys the frontend build.
3. Run `npx convex deploy` from `frontend/` to push the schema and `evals.ts` mutations to the production Convex deployment.
4. Verify in the Convex dashboard: after submitting a real question on the live app, an `evals` record appears with non-zero `input_tokens`, `output_tokens`, and `latency_ms`.
