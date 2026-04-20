"""
retrieval.py — Qdrant + Voyage AI context lookup.

Exposes retrieve_context(question, top_k, source) -> str.
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


def retrieve_context(question: str, top_k: int = 5, source: str | None = None) -> str:
    """Embed question, query Qdrant, return formatted doc block or "" on failure.

    source: 'clerk' | 'mdn' | None (search all).
    """
    if _qdrant is None or _voyage is None:
        logging.warning("retrieve_context: client(s) not initialized — skipping")
        return ""
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
        if not hits:
            return ""
        lines = ["--- RETRIEVED DOCS ---"]
        for hit in hits:
            hit_source = hit.payload.get("source", "")
            path = hit.payload.get("repo_path", "")
            text = hit.payload.get("text", "")
            lines.append(f"[{hit_source} - {path}]")
            lines.append(text)
            lines.append("")
        lines.append("--- END DOCS ---")
        return "\n".join(lines)
    except Exception as e:
        logging.warning("retrieve_context failed: %s", e)
        return ""
