"""
retrieval.py — Qdrant + Voyage AI context lookup.

Exposes retrieve_context(question) -> str.
Returns a formatted doc block on success, "" on any failure.
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


def retrieve_context(question: str, top_k: int = 5) -> str:
    """Embed question, query Qdrant, return formatted doc block or "" on failure."""
    if _qdrant is None or _voyage is None:
        logging.warning("retrieve_context: client(s) not initialized — skipping")
        return ""
    try:
        result = _voyage.embed([question], model="voyage-3.5-lite", input_type="query")
        vector = result.embeddings[0]
        hits = _qdrant.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=top_k,
        ).points
        if not hits:
            return ""
        lines = ["--- RETRIEVED DOCS ---"]
        for hit in hits:
            source = hit.payload.get("source", "")
            path = hit.payload.get("repo_path", "")
            text = hit.payload.get("text", "")
            lines.append(f"[{source} - {path}]")
            lines.append(text)
            lines.append("")
        lines.append("--- END DOCS ---")
        return "\n".join(lines)
    except Exception as e:
        logging.warning("retrieve_context failed: %s", e)
        return ""
