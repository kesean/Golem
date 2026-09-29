"""
retrieval.py — Qdrant + Voyage AI context lookup.

Exposes retrieve_chunks(question, top_k, source) -> list[dict] and
retrieve_context_and_chunks(question, top_k, source) -> (str, list[dict]).
Both return "empty" ([] or ("", [])) on any failure, never raise.
Clients initialized once at import time; None when env vars are absent.
"""

import os
import logging
import re

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
_SOURCE_NAMES = {"clerk": "Clerk", "mdn": "MDN"}


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
      (Note: MDN paths keep the repo's lowercase slug in the URL; MDN itself redirects to canonical casing)

    Path safety: Returns None if path contains newlines, control chars, spaces, '?', '#', '@',
    or '..' segments, or has empty segments ('//'), or the remainder doesn't match [A-Za-z0-9._~/-]+.
    """
    # Normalize source name for case-insensitive comparison
    source_lower = source.lower() if source else ""

    def _is_safe_path_remainder(rest: str) -> bool:
        """Check if path remainder is safe: only [A-Za-z0-9._~/-], no '..' or '//'."""
        if not rest:
            return True  # Empty is safe (for top-level index case)
        # Check for '..' segments
        if ".." in rest:
            return False
        # Check for empty segments (//)
        if "//" in rest:
            return False
        # Check that remainder matches the safe pattern [A-Za-z0-9._~/-]
        # fullmatch (not `$`, which tolerates a trailing "\n") also rejects control chars and ?#@ space
        if not re.fullmatch(r"[A-Za-z0-9._~/-]+", rest):
            return False
        return True

    def _check_safe_path(path: str) -> bool:
        """Check if path has no empty segments (//)."""
        return "//" not in path

    if source_lower == "clerk":
        # Clerk: docs/<rest>.mdx
        if not path.startswith("docs/") or not path.endswith(".mdx"):
            return None
        # Check for '//' in the full path (empty segments)
        if not _check_safe_path(path):
            return None
        # Remove "docs/" prefix and ".mdx" suffix
        rest = path[5:-4]  # Remove "docs/" (5 chars) and ".mdx" (4 chars)
        # Remove trailing "/index" if present
        if rest.endswith("/index"):
            rest = rest[:-6]
        # Also handle bare "index" case (for docs/index.mdx)
        elif rest == "index":
            rest = ""
        # Validate the remainder
        if not _is_safe_path_remainder(rest):
            return None
        # Handle top-level index: empty rest -> "https://clerk.com/docs"
        if rest == "":
            return "https://clerk.com/docs"
        return f"https://clerk.com/docs/{rest}"

    elif source_lower == "mdn":
        # MDN: files/en-us/<rest>/index.md
        if not path.startswith("files/en-us/") or not path.endswith("/index.md"):
            return None
        # Check for '//' in the full path (empty segments)
        if not _check_safe_path(path):
            return None
        # Remove "files/en-us/" prefix (12 chars) and "/index.md" suffix (9 chars)
        rest = path[12:-9]
        # Validate the remainder
        if not _is_safe_path_remainder(rest):
            return None
        # For MDN, empty rest (just the index.md) returns None as it's not a valid doc
        if not rest:
            return None
        return f"https://developer.mozilla.org/en-US/docs/{rest}"

    # Unknown source
    return None


def retrieve_chunks(question: str, top_k: int = 5, source: str | None = None) -> list[dict]:
    """Embed question, query Qdrant, return matching chunks as a list of
    {"source", "path", "text", "url"} dicts, most relevant first. [] on any failure.

    source: case-insensitive source name ('clerk', 'mdn', 'Clerk', 'MDN', etc.) or None (search all).
            'clerk' and 'mdn' are normalized to their canonical payload names ('Clerk', 'MDN').
            Unknown sources pass through unchanged.
    """
    if _qdrant is None or _voyage is None:
        logging.warning("retrieve_chunks: client(s) not initialized — skipping")
        return []
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        result = _voyage.embed([question], model="voyage-3.5-lite", input_type="query")
        vector = result.embeddings[0]

        # Payload stores canonical names; accept any case/padding ('clerk', ' MDN '). Unknown values pass through.
        normalized_source = _SOURCE_NAMES.get(source.strip().lower(), source.strip()) if source else None

        query_filter = Filter(
            must=[FieldCondition(key="source", match=MatchValue(value=normalized_source))]
        ) if normalized_source else None
        hits = _qdrant.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
        ).points
        return [
            {
                "source": hit.payload.get("source") or "",
                "path": hit.payload.get("repo_path") or "",
                "text": hit.payload.get("text") or "",
                "url": canonical_url(hit.payload.get("source") or "", hit.payload.get("repo_path") or ""),
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
        # Sanitize source and path for header injection: replace \r and \n with space
        source_sanitized = chunk['source'].replace('\r', ' ').replace('\n', ' ')
        path_sanitized = chunk['path'].replace('\r', ' ').replace('\n', ' ')
        lines.append(f"[{source_sanitized} - {path_sanitized}]")
        if chunk.get("url"):
            lines.append(f"URL: {chunk['url']}")
        lines.append(chunk["text"])
        lines.append("")
    lines.append("--- END DOCS ---")
    return "\n".join(lines), chunks
