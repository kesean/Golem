"""
retrieval.py — Qdrant + Voyage AI context lookup.

Exposes retrieve_chunks(question, top_k, source) -> list[dict] and
retrieve_context_and_chunks(question, top_k, source) -> (str, list[dict]).
Both return "empty" ([] or ("", [])) on any failure, never raise.
Clients initialized once at import time; None when env vars are absent.
"""

import os
import logging

_qdrant = None
_voyage = None

_qdrant_url = os.getenv("QDRANT_URL", "")
_qdrant_api_key = os.getenv("QDRANT_API_KEY", "")
_voyage_api_key = os.getenv("VOYAGE_API_KEY", "")

if _qdrant_url and _qdrant_api_key:
    try:
        from qdrant_client import QdrantClient
        _qdrant = QdrantClient(url=_qdrant_url, api_key=_qdrant_api_key)
    except Exception as e:
        logging.warning("retrieval: failed to init Qdrant client: %s", e)

if _voyage_api_key:
    try:
        import voyageai
        _voyage = voyageai.Client(api_key=_voyage_api_key)
    except Exception as e:
        logging.warning("retrieval: failed to init Voyage client: %s", e)

COLLECTION = "dev_support_docs"


def canonical_url(source: str, path: str) -> str | None:
    """Convert a repo path to its canonical public URL.

    Args:
        source: The documentation source name ("Clerk", "MDN", etc.)
        path: The repository path to the file

    Returns:
        The canonical URL as a string, or None if the source/path is unknown.

    Mapping rules:
    - Clerk: docs/<rest>.mdx → https://clerk.com/docs/<rest> (drop .mdx, drop trailing /index)
    - MDN: files/en-us/<rest>/index.md → https://developer.mozilla.org/en-US/docs/<rest>
    """
    # Normalize source name for case-insensitive comparison
    source_lower = source.lower() if source else ""

    if source_lower == "clerk":
        # Clerk: docs/<rest>.mdx
        if not path.startswith("docs/") or not path.endswith(".mdx"):
            return None
        # Remove "docs/" prefix and ".mdx" suffix
        rest = path[5:-4]  # Remove "docs/" (5 chars) and ".mdx" (4 chars)
        # Remove trailing "/index" if present
        if rest.endswith("/index"):
            rest = rest[:-6]
        return f"https://clerk.com/docs/{rest}"

    elif source_lower == "mdn":
        # MDN: files/en-us/<rest>/index.md
        if not path.startswith("files/en-us/") or not path.endswith("/index.md"):
            return None
        # Remove "files/en-us/" prefix (12 chars) and "/index.md" suffix (9 chars)
        rest = path[12:-9]
        return f"https://developer.mozilla.org/en-US/docs/{rest}"

    # Unknown source
    return None


def retrieve_chunks(question: str, top_k: int = 5, source: str | None = None) -> list[dict]:
    """Embed question, query Qdrant, return matching chunks as a list of
    {"source", "path", "text", "url"} dicts, most relevant first. [] on any failure.

    source: 'clerk' | 'mdn' | None (search all).
    """
    if _qdrant is None or _voyage is None:
        logging.warning("retrieve_chunks: client(s) not initialized — skipping")
        return []
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        result = _voyage.embed([question], model="voyage-3.5-lite", input_type="query")
        vector = result.embeddings[0]
        query_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=source))]
        ) if source else None
        hits = _qdrant.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
        ).points
        return [
            {
                "source": hit.payload.get("source", ""),
                "path": hit.payload.get("repo_path", ""),
                "text": hit.payload.get("text", ""),
                "url": canonical_url(hit.payload.get("source", ""), hit.payload.get("repo_path", "")),
            }
            for hit in hits
        ]
    except Exception as e:
        logging.warning("retrieve_chunks failed: %s", e)
        return []


def retrieve_context_and_chunks(question: str, top_k: int = 5, source: str | None = None) -> tuple[str, list[dict]]:
    """Like retrieve_chunks, but also returns the chunks formatted as a doc
    block ready to inject into the prompt. ("", []) when nothing is found.
    """
    chunks = retrieve_chunks(question, top_k=top_k, source=source)
    if not chunks:
        return "", []
    lines = ["--- RETRIEVED DOCS ---"]
    for chunk in chunks:
        lines.append(f"[{chunk['source']} - {chunk['path']}]")
        if chunk.get("url"):
            lines.append(f"URL: {chunk['url']}")
        lines.append(chunk["text"])
        lines.append("")
    lines.append("--- END DOCS ---")
    return "\n".join(lines), chunks
