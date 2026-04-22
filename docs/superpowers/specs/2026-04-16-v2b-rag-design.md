# V2b RAG Pipeline — Design Spec

**Date:** 2026-04-16
**Status:** Approved

---

## Overview

Add a retrieval-augmented generation (RAG) pipeline to the dev support chatbot. When a user submits a question, the backend retrieves the most relevant documentation chunks from a vector database and injects them into the prompt as grounding context. This improves response accuracy for questions about Clerk and MDN web APIs.

---

## Goals

- Embed targeted sections of Clerk and MDN documentation into a Qdrant Cloud vector collection
- On every `/ask` request, retrieve the top-5 most relevant chunks and prepend them to the user's question
- Degrade gracefully — if retrieval fails for any reason, the request continues without RAG rather than erroring out

## Non-Goals

- No Vercel docs (no public GitHub source confirmed — deferred to V2c)
- No Anthropic docs
- No query classifier (V2c)
- No per-source retrieval routing
- No in-app display of retrieved chunks (V2d)
- No streaming changes

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `retrieval.py` | Qdrant + Voyage clients; `retrieve_context()` function |
| `scripts/embed_docs.py` | One-off ingestion script: fetch then chunk then embed then upsert |
| `tests/test_retrieval.py` | Unit tests for `retrieval.py` |
| `tests/test_prompt.py` | Unit tests for updated `build_messages()` |

### Modified Files

| File | Change |
|------|--------|
| `prompt.py` | `build_messages()` gains optional `context: str` parameter |
| `app.py` | `/ask` calls `retrieve_context(question)` before the LLM call; timer moved to before `retrieve_context()` |
| `requirements.txt` | Add `qdrant-client`, `voyageai`, `tiktoken`, `httpx` |

### New Environment Variables

| Variable | Purpose |
|----------|---------|
| `QDRANT_URL` | Qdrant Cloud cluster URL |
| `QDRANT_API_KEY` | Qdrant Cloud API key |
| `VOYAGE_API_KEY` | Voyage AI API key |
| `GITHUB_TOKEN` | Optional — raises GitHub API rate limit from 60 to 5000 req/hr |

---

## Data Flow

```
User question
     |
     v
start = time.time()                   <- timer starts here (includes retrieval)
     |
     v
retrieve_context(question)
  +-- Embed question via Voyage AI voyage-3.5-lite (input_type="query")
  +-- Query Qdrant dev_support_docs (top-5, cosine similarity)
     |
     v
build_messages(question, history, context)
  +-- Prepends retrieved docs block to user turn
     |
     v
client.messages.create(...)
     |
     v
latency_ms = round((time.time() - start) * 1000)   <- includes retrieval + LLM
```

---

## Doc Corpus

### Sources and Target Paths

All paths are **explicit file lists** hardcoded as constants at the top of `embed_docs.py`. No directory scanning — the GitHub contents API is called per-file, not per-directory. This avoids pagination complexity and keeps the corpus intentional.

**Clerk** (`clerk/clerk-docs`, branch `main`)

File list constants target:
- `docs/authentication/` — sessions, tokens, JWT templates
- `docs/backend-requests/` — verifying sessions, middleware
- `docs/errors/` — error codes and troubleshooting

**MDN** (`mdn/content`, branch `main`)

File list constants target:
- `files/en-us/web/api/fetch_api/` — Fetch API reference
- `files/en-us/web/api/headers/` — Headers interface
- `files/en-us/web/api/request/` — Request interface
- `files/en-us/web/api/response/` — Response interface
- `files/en-us/web/http/status/` — HTTP status codes
- `files/en-us/web/http/cors/` — CORS reference

### Chunking

- Chunk size: ~500 tokens (measured with `tiktoken`, model `cl100k_base`)
- Overlap: 50 tokens
- Split on paragraph/heading boundaries where possible
- Chunk ID: deterministic hash of `repo_path + chunk_index` (ensures idempotent upserts)

### Qdrant Collection

- Name: `dev_support_docs`
- Similarity: cosine
- Vector dimension: 512 (voyage-3.5-lite default)
- Payload metadata per chunk: `{ source, repo_path, github_url, chunk_index }`
- Collection created by `embed_docs.py` on first run; subsequent runs upsert by chunk ID

---

## `retrieval.py`

```python
# Public interface
def retrieve_context(question: str, top_k: int = 5) -> str
```

- Module-level Qdrant and Voyage clients initialized once on import (same pattern as `client = Anthropic()` in `app.py`)
- Embeds question with `voyage-3.5-lite`, `input_type="query"`
- Queries `dev_support_docs` for top-k chunks
- Returns formatted string using plain-text delimiters (not XML, to avoid conflict with the system prompt's XML output format):

```
--- RETRIEVED DOCS ---
[Clerk - docs/authentication/sessions.mdx]
...chunk text...

[MDN - files/en-us/web/api/fetch_api/index.md]
...chunk text...
--- END DOCS ---
```

- Returns `""` on any failure (missing env vars, network error, empty results) — logs a warning, does not raise

---

## `prompt.py` Changes

```python
def build_messages(
    question: str,
    history: list | None = None,
    context: str = "",
) -> list:
    user_content = f"{context}\n\n{question}".strip() if context else question
    messages = list(history or [])
    messages.append({"role": "user", "content": user_content})
    return messages
```

Backward compatible — existing callers with no `context` argument continue to work.

---

## `app.py` Changes

```python
start = time.time()                                        # moved: now before retrieval
context = retrieve_context(question)
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=2048,
    system=SYSTEM_PROMPT,
    messages=build_messages(question, history, context),   # context added
)
latency_ms = round((time.time() - start) * 1000)
```

`latency_ms` now includes retrieval time, keeping the V2a observability data accurate.

---

## `scripts/embed_docs.py`

- Source file paths defined as explicit constants at the top of the file (one list per source)
- Fetches each file's raw content via the GitHub contents API (`https://api.github.com/repos/{owner}/{repo}/contents/{path}`)
- Decodes base64 content from the API response
- Tokenizes with `tiktoken` (`cl100k_base`) and splits into ~500-token chunks with 50-token overlap
- Embeds chunks in batches of up to 128 via Voyage AI `voyage-3.5-lite` with `input_type="document"`
- Creates the `dev_support_docs` Qdrant collection if it does not exist (cosine, 512 dims)
- Upserts all chunks using deterministic IDs
- Prints progress per source: `Clerk: 12 files, 148 chunks`
- Fails fast on any error with a non-zero exit code

```bash
python scripts/embed_docs.py
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `QDRANT_URL` / `VOYAGE_API_KEY` missing | `retrieve_context` logs warning, returns `""` |
| Qdrant or Voyage network error | `retrieve_context` catches exception, returns `""` |
| Empty retrieval results | Returns `""` |
| `embed_docs.py` failure | Prints error, exits non-zero |

The `/ask` route never returns an error due to retrieval failure.

---

## Testing

### `tests/test_retrieval.py` (new)

Mock both the Voyage and Qdrant clients at the module level.

- Returns formatted doc block when Qdrant returns results
- Returns `""` when Qdrant returns no results
- Returns `""` when `QDRANT_URL` env var is missing
- Returns `""` when `VOYAGE_API_KEY` env var is missing
- Returns `""` when the Voyage embed call raises an exception
- Returns `""` when the Qdrant query call raises an exception

### `tests/test_prompt.py` (new)

- `build_messages(question, history)` with no context produces identical output to today (no regression)
- `build_messages(question, history, context)` with a non-empty context prepends the doc block to the user turn

### `tests/test_routes.py` (modified)

All existing tests get an `autouse` fixture in `conftest.py` that mocks `app.retrieve_context` to return `""`:

```python
@pytest.fixture(autouse=True)
def mock_retrieval(monkeypatch):
    monkeypatch.setattr("app.retrieve_context", lambda q: "")
```

New test: mock `retrieve_context` to return a non-empty doc block, assert the doc block appears in the `messages` argument passed to `client.messages.create`.

### E2E

No Playwright changes — retrieval quality is validated manually via the Convex evaluations table.
