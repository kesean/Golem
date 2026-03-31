# Spec: Revert Streaming to Standard JSON Response

**Date:** 2026-03-30
**Branch:** feature/phase-8-production
**Type:** Cleanup / Pre-deployment optimization

---

## Summary

Remove the streaming response implementation from `/ask/stream` and replace it with a standard synchronous JSON response from a renamed `/ask` endpoint. The frontend already accumulates the full stream before rendering, so users will see no behavioral change. This simplifies both the backend and frontend code and removes streaming compatibility concerns ahead of the AWS App Runner deployment.

---

## Motivation

- The frontend reads the full stream into `accumulated` before calling `renderResponse()` — streaming provides zero UX benefit today
- `stream_with_context` and `ReadableStream` reader loops add complexity with no payoff
- Standard JSON responses are universally compatible with load balancers, proxies, and App Runner without extra configuration
- Simpler code is easier to test and maintain

---

## Architecture

No structural changes. The same request/response cycle applies — the only change is the transport mechanism: chunked `text/plain` stream → single `application/json` response.

```
Frontend                    Backend                     Claude API
   |                           |                             |
   | POST /ask                 |                             |
   | { question, history }     |                             |
   |-------------------------->|                             |
   |                           | messages.create(...)        |
   |                           |---------------------------->|
   |                           |         full XML response   |
   |                           |<----------------------------|
   |                           |                             |
   | 200 { response: "<xml>" } |                             |
   |<--------------------------|                             |
   | res.json() → renderResponse()                          |
```

---

## Changes

### Backend — `app.py`

- Rename route: `/ask/stream` → `/ask`
- Replace `client.messages.stream(...)` with `client.messages.create(...)`
- Remove `generate()` inner function
- Remove `stream_with_context`, `Response` from the response — return `jsonify({ "response": text })` instead
- Remove unused imports: `Response`, `stream_with_context`
- Keep all existing auth (`@require_auth`), rate limiting (`@limiter.limit`), and input validation logic untouched

### Frontend — `frontend/src/app.js`

- Update fetch URL: `/ask/stream` → `/ask`
- Remove `ReadableStream` reader loop (the `reader`, `decoder`, `accumulated` loop)
- Replace with: `const { response } = await res.json()`
- Pass `response` directly to `renderResponse(response)` — same as before
- All downstream logic (conversation history, Convex save, sidebar render) unchanged

### What is NOT changed

- `renderResponse()` and `extractSection()` — identical, XML parsing still needed
- Convex history schema and mutations
- Auth headers and token logic
- Error handling and loading skeleton
- Rate limiter configuration
- `prompt.py` — system prompt and `build_messages` unchanged

---

## Testing

- Manual: submit a question, verify structured response renders correctly
- Manual: verify error states still work (empty question, network error)
- Existing unit tests in `tests/` should pass without modification
- No new tests required — behavior is identical, only transport changes

---

## Risks

None significant. The `closed` property returned by `extractSection()` will always be `true` after this change (it was a streaming artifact for detecting partial tags). It is harmless and can be cleaned up in a future pass.
