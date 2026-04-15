# V2a Observability — Design Spec

**Date:** 2026-04-14
**Status:** Approved

---

## Overview

Add observability to every `/ask` request: capture token usage and latency from the Claude API response, store it in a Convex `evals` table alongside user feedback, and surface thumbs up/down buttons on each response card in the UI. No in-app stats view — data is queried directly from the Convex dashboard.

---

## Goals

- Log `input_tokens`, `output_tokens`, and `latency_ms` on every `/ask` request
- Store eval records in Convex for dashboard-level analysis
- Allow the user to rate each response (thumbs up / thumbs down) from the chat UI
- Link feedback to the correct eval record via a Convex record ID

## Non-Goals

- No in-app stats page or dashboard
- No per-user or aggregate stats UI
- No streaming changes
- No changes to auth, rate limiting, or the `history` table

---

## Architecture

### Data Flow

1. Flask records `start = time.time()` before `client.messages.create()`
2. After the call, computes `latency_ms = round((time.time() - start) * 1000)`
3. Reads `message.usage.input_tokens` and `message.usage.output_tokens` from the response object
4. Returns all metrics alongside the existing `response` field:

```json
{
  "response": "<xml>...",
  "input_tokens": 312,
  "output_tokens": 489,
  "latency_ms": 1840
}
```

5. Frontend receives the response, writes an eval record to Convex via `createEval` mutation
6. Convex returns the new record's `_id`
7. Frontend stores `evalId` as a `data-eval-id` attribute on the response card
8. Thumbs up/down buttons call `setFeedback(evalId, feedback)` mutation to patch the record

---

## Convex Schema

New `evals` table added to `schema.ts` alongside the existing `history` table:

```ts
evals: defineTable({
  userId:        v.string(),
  question:      v.string(),
  response:      v.string(),
  latency_ms:    v.number(),
  input_tokens:  v.number(),
  output_tokens: v.number(),
  feedback:      v.optional(v.union(v.literal("up"), v.literal("down"))),
}).index("by_user", ["userId"])
```

- `feedback` is optional — records are created without it and patched later if the user rates
- `createdAt` is not stored explicitly; Convex's `_creationTime` serves this purpose

---

## Components & Changes

### `app.py`
- Add `start = time.time()` before `client.messages.create()`
- Compute `latency_ms` after the call
- Read `message.usage.input_tokens` and `message.usage.output_tokens`
- Extend the JSON response to include `latency_ms`, `input_tokens`, `output_tokens`
- No new routes, no new dependencies

### `frontend/convex/schema.ts`
- Add `evals` table definition (see above)

### `frontend/convex/evals.ts` (new file)
- `createEval` mutation — derives `userId` from `ctx.auth.getUserIdentity().tokenIdentifier` (same pattern as `history.add`), inserts a new eval record, returns `_id`
- `setFeedback` mutation — patches `feedback` field on an existing eval record by ID; verifies the record belongs to the calling user before patching

### `frontend/src/app.js`
- In `askQuestion()`: destructure `input_tokens`, `output_tokens`, `latency_ms` from the `/ask` response
- Call `createEval` mutation after a successful response, store returned ID on the card as `data-eval-id`
- Render thumbs up/down buttons on the response card after content is ready
- Wire buttons to `setFeedback` mutation; handle toggle and switch behaviour

### `frontend/src/style.css`
- Add `.feedback-btn` class (base: matches `.copy-btn`)
- Add `.feedback-btn.active-up` — teal highlight (`var(--teal)`, `rgba(89,201,165,0.15)` bg)
- Add `.feedback-btn.active-down` — coral highlight (`var(--coral)`, `rgba(239,111,108,0.13)` bg)
- Add `.feedback-btn:disabled` — `opacity: 0.35`, `cursor: not-allowed`
- All transitions: `all 0.15s`

---

## UI Design

**Placement:** Inside `.response-actions` alongside Copy and Share — same row, same size.

**Icons:** Small inline SVGs (not emoji). Upward thumb and downward thumb at the weight of the existing UI. No text labels.

**States:**

| State | Color | Background | Border |
|-------|-------|------------|--------|
| Base | `var(--text-3)` | transparent | `var(--border)` |
| Hover | `var(--teal)` | `rgba(89,201,165,0.07)` | `rgba(89,201,165,0.4)` |
| Active up | `var(--teal)` | `rgba(89,201,165,0.15)` | `rgba(89,201,165,0.4)` |
| Active down | `var(--coral)` | `rgba(239,111,108,0.13)` | `rgba(239,111,108,0.28)` |
| Disabled | `var(--text-3)` at 35% opacity | transparent | `var(--border)` |

**Interaction:**
- Buttons are disabled while the response is loading
- Clicking an active button deactivates it (sets `feedback: null`)
- Clicking the opposite button switches the selection
- Only one button can be active at a time

---

## Testing

- Manual: submit a question, verify eval record appears in Convex dashboard with correct tokens/latency
- Manual: click thumbs up, verify `feedback: "up"` is patched; toggle off, verify `null`; switch to thumbs down, verify `feedback: "down"`
- Manual: verify buttons are disabled during loading, enabled after response
- Existing tests in `tests/` should pass unchanged (no Flask route signature changes)
