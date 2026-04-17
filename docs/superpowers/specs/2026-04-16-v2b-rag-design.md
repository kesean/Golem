# V2b RAG Pipeline — Design Spec

**Date:** 2026-04-16
**Status:** Approved

---

## Overview

Add a retrieval-augmented generation (RAG) pipeline to the dev support chatbot. When a user submits a question, the backend retrieves the most relevant documentation chunks from a vector database and injects them into the prompt as grounding context. This improves response accuracy for questions about Clerk, MDN web APIs, and Vercel.

---

## Goals

- Embed targeted sections of Clerk, MDN, and Vercel documentation into a Qdrant Cloud vector collection
- On every `/ask` request, retrieve the top-5 most relevant chunks and prepend them to the user's question
- Degrade gracefully — if retrieval fails for any reason, the request continues without RAG rather than erroring out

## Non-Goals

- No query classifier (that's V2c)
- No per-source retrieval routing
- No in-app display of retrieved chunks (that's V2d)
- No streaming changes
- No Anthropic docs (narrowed to Clerk, MDN, Vercel)

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `retrieval.py` | Qdrant + Voyage clients; `retrieve_context()` function |
| `scripts/embed_docs.py` | One-off ingestion script: fetch → chunk → embed → upsert |
| `tests/test_retrieval.py` | Unit tests for `retrieval.py` |
| `tests/test_prompt.py` | Unit tests for updated `build_messages()` |

### Modified Files

| File | Change |
|------|--------|
| `prompt.py` | `build_messages()` gains optional `context: str` parameter |
| `app.py` | `/ask` calls `retrieve_context(question)` and passes result to `build_messages()` |
| `requirements.txt` | Add `qdrant-client`, `voyageai` |

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
     │
     ▼
retrieve_context(question)
  ├── Embed question via Voyage AI voyage-3-lite
  └── Query Qdrant dev_support_docs (top-5, cosine similarity)
     │
     ▼
build_messages(question, history, context)
  └── Prepends <context>...</context> block to user turn
     │
     ▼
client.messages.create(...)  ← unchanged
```

---

## Doc Corpus

### Sources and Target Paths

**Clerk** (`clerkinc/clerk-docs`, `/docs`)
- `authentication/` — sessions, tokens, JWT templates
- `backend-requests/` — verifying sessions, middleware
- `errors/` — error codes and troubleshooting

**MDN** (`mdn/content`, `/files/en-us/web`)
- `api/fetch/` — Fetch API reference
- `api/headers/` — Headers interface
- `api/request/` — Request interface
- `api/response/` — Response interface
- `http/status/` — HTTP status codes
- `http/cors/` — CORS reference

**Vercel** (repo TBD — confirm during implementation; likely `vercel/vercel-docs`)
- `deployments/` — build and deploy pipeline
- `environment-variables/` — env var configuration
- `errors/` — deployment error reference
- `frameworks/` — framework-specific guides

### Chunking

- Chunk size: ~500 tokens
- Overlap: 50 tokens
- Split on paragraph/heading boundaries where possible
- Chunk ID: deterministic hash of `repo_path + chunk_index` (ensures idempotent upserts)

### Qdrant Collection

- Name: `dev_support_docs`
- Similarity: cosine
- Vector dimension: 512 (voyage-3-lite)
- Payload metadata per chunk: `{ source, repo_path, github_url, chunk_index }`

---

## `retrieval.py`

```python
# Public interface
def retrieve_context(question: str, top_k: int = 5) -> str
```

- Module-level Qdrant and Voyage clients initialized once on import
- Embeds question with `voyage-3-lite`
- Queries `dev_support_docs` for top-k chunks
- Returns formatted string:

```
<context>
[Clerk – authentication/sessions.mdx]
...chunk text...

[MDN – web/api/fetch/index.md]
...chunk text...
</context>
```

- Returns `""` on any failure (missing env vars, network error, empty results) — logs a warning but does not raise

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

Backward compatible — existing callers with no `context` argument are unaffected.

---

## `scripts/embed_docs.py`

- Reads target file lists per source from hardcoded constants at the top of the file
- Fetches raw markdown via the GitHub contents API
- Chunks, embeds (batched, up to 128 texts per Voyage request), upserts to Qdrant
- Idempotent — re-running overwrites via deterministic chunk IDs
- Prints progress per source: `Clerk: 12 files, 148 chunks`
- Fails fast on errors with a non-zero exit code

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

- Returns formatted context string when Qdrant returns results (mock Voyage + Qdrant)
- Returns `""` when Qdrant returns no results
- Returns `""` when env vars are missing
- Returns `""` when Voyage call raises an exception

### `tests/test_prompt.py` (new)

- `build_messages` with `context=""` produces same output as today (no regression)
- `build_messages` with context prepends the context block to the user turn

### `tests/test_routes.py` (modified)

- Existing tests unchanged (`retrieve_context` mocked to return `""`)
- New test: mock `retrieve_context` returning non-empty context, assert it appears in messages passed to `client.messages.create`

### E2E

No Playwright changes — retrieval quality is validated manually via Convex eval records.
