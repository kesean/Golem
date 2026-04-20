# V2c Orchestration + Tools — Design Spec

**Goal:** Replace the V2b unconditional pre-fetch with Claude-native tool_use. Claude decides when to call `retrieve_docs` (Qdrant search with source filter) and `api_lookup` (live Clerk/Anthropic HTTP fetch). Frontend and response format are unchanged.

**Tech Stack:** Flask · Anthropic Python SDK (tool_use) · Qdrant · Voyage AI · httpx · pytest

---

## Architecture

The `/ask` route delegates entirely to `chat.run(question, history)`. `chat.py` drives a multi-turn tool loop — calling Claude, dispatching any requested tools, feeding results back — until Claude returns `stop_reason == "end_turn"` or `MAX_TOOL_ROUNDS` is exceeded.

### Request Lifecycle

```
Frontend → POST /ask { question, history }
  → app.py: chat.run(question, history)
    → chat.py: call Claude with TOOLS declared
      → Claude: stop_reason == "tool_use"
        → _dispatch_tool() routes each call:
            retrieve_docs → retrieval.retrieve_context(query, source)
            api_lookup    → api_lookup.fetch(service, endpoint, params)
        → tool results sent back as tool_result messages
      → Claude: stop_reason == "end_turn" → final XML answer
  → app.py: return { response, input_tokens, output_tokens, latency_ms }
```

`MAX_TOOL_ROUNDS = 3` — hard cap on loop iterations. Exceeding it raises `RuntimeError`, which Flask handles as a 502.

---

## Files

| Action | File | Purpose |
|--------|------|---------|
| Create | `chat.py` | Tool loop orchestration — `run()` + `_dispatch_tool()` |
| Create | `api_lookup.py` | Clerk + Anthropic live HTTP fetch — hard URL allowlist |
| Create | `tests/test_chat.py` | Tool loop unit tests |
| Create | `tests/test_api_lookup.py` | api_lookup unit tests |
| Modify | `retrieval.py` | Add optional `source` filter param |
| Modify | `prompt.py` | Remove `context` param from `build_messages()` |
| Modify | `app.py` | Replace direct Claude call with `chat.run()` |
| Modify | `tests/test_routes.py` | Patch `chat.run` instead of `client.messages.create` |

---

## Module Design

### chat.py

Public interface:

```python
def run(question: str, history: list) -> dict:
    """Run tool loop. Returns { response, input_tokens, output_tokens, latency_ms }."""
```

Internal:

```python
def _dispatch_tool(name: str, inputs: dict) -> str:
    """Route tool call to retrieval or api_lookup. Returns string result."""

TOOLS = [retrieve_docs_schema, api_lookup_schema]
MAX_TOOL_ROUNDS = 3
```

Loop logic: call Claude → if `stop_reason == "tool_use"` → dispatch all tool calls in the response → append `tool_result` messages → call Claude again → repeat until `end_turn` or rounds exhausted.

Token counts are accumulated across all loop iterations. `latency_ms` covers the full loop.

### api_lookup.py

```python
def fetch(service: str, endpoint: str, params: dict | None) -> str:
    """service: 'clerk' | 'anthropic'. Returns formatted string or error message."""
```

Hard URL allowlist — Claude cannot instruct it to fetch arbitrary URLs:

```python
CLERK_ENDPOINTS = {
    "errors": "https://api.clerk.com/v1/errors",
    "jwks":   "https://{clerk_domain}/.well-known/jwks.json",  # {clerk_domain} substituted from CLERK_DOMAIN env var
}
ANTHROPIC_ENDPOINTS = {
    "models": "https://api.anthropic.com/v1/models",
}
```

Credentials loaded from env vars: `CLERK_SECRET_KEY`, `CLERK_DOMAIN`, `ANTHROPIC_API_KEY`. Uses `httpx` with a 10-second timeout. Returns a formatted string for Claude to reason over, or a plain error message on failure.

### retrieval.py (modified)

Before (V2b):
```python
def retrieve_context(question: str, top_k: int = 5) -> str
```

After (V2c) — backward-compatible:
```python
def retrieve_context(question: str, top_k: int = 5, source: str | None = None) -> str:
    """source: 'clerk' | 'mdn' | None (search all)."""
```

When `source` is provided, adds a Qdrant `must` filter on the `source` payload field.

### prompt.py (modified)

`build_messages(question, history)` — drop the `context` param added in V2b. Context is now delivered via tool results, not pre-injected into the user message.

---

## Tool Schemas

### retrieve_docs

```python
{
    "name": "retrieve_docs",
    "description": (
        "Search embedded documentation for relevant context. "
        "Use when the question is about Clerk auth, JWT, MDN web APIs, "
        "or general developer concepts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query":  {"type": "string", "description": "Search query"},
            "source": {
                "type": ["string", "null"],
                "enum": ["clerk", "mdn", None],
                "description": "Filter to a specific doc source, or null to search all.",
            },
        },
        "required": ["query"],
    },
}
```

### api_lookup

```python
{
    "name": "api_lookup",
    "description": (
        "Fetch live data from the Clerk or Anthropic API. "
        "Use for error codes, JWKS keys, or current model information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service":  {"type": "string", "enum": ["clerk", "anthropic"]},
            "endpoint": {"type": "string", "description": "Endpoint key from the allowlist"},
            "params":   {"type": ["object", "null"], "description": "Optional query params"},
        },
        "required": ["service", "endpoint"],
    },
}
```

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| `retrieve_docs` fails (Qdrant/Voyage error) | Return `"No docs found."` as tool result — Claude answers from training data |
| `api_lookup` endpoint not in allowlist | Return `"Error: endpoint not permitted."` — no HTTP call made |
| `api_lookup` HTTP 4xx/5xx or timeout | Return `"Error: <status> from <service>."` — Claude explains service unavailable |
| Tool loop exceeds `MAX_TOOL_ROUNDS` | Raise `RuntimeError` → Flask 502 |
| Unknown tool name requested | Return `"Error: unknown tool."` — logged as warning |

Tool failures are always returned as `tool_result` strings — never raised as exceptions mid-loop. Only loop-level failures propagate up to Flask.

---

## Testing

### New: tests/test_chat.py
Mock: `chat._client.messages.create` (the module-level Anthropic client initialized in `chat.py`)

- No tool call → returns final answer directly
- Single `retrieve_docs` call → dispatches, injects result, returns answer
- Single `api_lookup` call → dispatches, injects result, returns answer
- Both tools called in same turn
- Tool fails → error string returned, loop continues
- `MAX_TOOL_ROUNDS` exceeded → raises `RuntimeError`
- Unknown tool name → error string returned

### New: tests/test_api_lookup.py
Mock: `httpx.get`

- Valid Clerk endpoint → returns formatted string
- Valid Anthropic endpoint → returns formatted string
- Endpoint not in allowlist → returns error string (no HTTP call made)
- HTTP 4xx response → returns error string
- Network timeout → returns error string

### Modified: tests/test_retrieval.py
- `source="clerk"` adds Qdrant filter
- `source=None` searches all (existing behavior preserved)

### Modified: tests/test_routes.py
- Patch `chat.run` instead of `client.messages.create`
- Existing token/latency assertions unchanged

### TDD Order
1. `test_api_lookup.py` → `api_lookup.py`
2. `test_retrieval.py` (source filter) → `retrieval.py`
3. `test_chat.py` → `chat.py`
4. `test_routes.py` update → `app.py` + `prompt.py`
5. `pytest tests/ -v` — full suite green

No Playwright changes — frontend contract (XML response shape, button states) is unchanged.

---

## Environment Variables

New vars required (add to `.env` and `.env.example`):

| Var | Used by | Purpose |
|-----|---------|---------|
| `CLERK_SECRET_KEY` | `api_lookup.py` | Clerk Management API auth |
| `CLERK_DOMAIN` | `api_lookup.py` | Clerk instance domain for JWKS endpoint (e.g. `yourapp.clerk.accounts.dev`) |

Existing vars unchanged: `QDRANT_URL`, `QDRANT_API_KEY`, `VOYAGE_API_KEY`, `ANTHROPIC_API_KEY`.
