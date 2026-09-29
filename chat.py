"""
chat.py — Claude call orchestrator.

Exposes stream_run(question, history) -> generator of SSE-ready event dicts.
"""

import logging
import os
import re
import time
from typing import Optional
from urllib.parse import urlparse

import anthropic

import retrieval
from prompt import SYSTEM_PROMPT, build_messages

# ---------------------------------------------------------------------------
# Anthropic client — initialized once at module level
# ---------------------------------------------------------------------------

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

MODEL = "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_urls_from_text(text: str) -> list[str]:
    """Extract all http(s) URLs from a string.

    Returns a list of unique URLs found.
    """
    # Match http(s)://... URLs, stopping at whitespace, <>, ", ', or )
    # This pattern stops at common delimiters and punctuation
    pattern = r'https?://[^\s<>"\')]+(?:\([^\)]*\))?[^\s<>"\')]*'
    urls = re.findall(pattern, text, re.IGNORECASE)

    # Strip trailing punctuation from each URL
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation like . , ; : ! ? etc.
        url = re.sub(r'[.,;:!?\'"«»…`*]+$', '', url)
        # Remove trailing parenthesis if unbalanced
        while url.endswith(')'):
            open_count = url.count('(')
            close_count = url.count(')')
            if close_count > open_count:
                url = url[:-1]
            else:
                break
        if url:
            cleaned_urls.append(url)

    return cleaned_urls


def _normalize_url(url: str) -> str:
    """Normalize a URL by stripping trailing slashes for comparison."""
    if not url:
        return url
    return url.rstrip('/')


def find_unretrieved_doc_urls(response_text: str, chunks: Optional[list[dict]]) -> list[str]:
    """Extract URLs from <docs> blocks not found in retrieved chunks.

    Args:
        response_text: The model's response containing <docs>...</docs> blocks
        chunks: List of retrieved chunk dicts with 'url' keys (may be empty/None)

    Returns:
        List of http(s) URLs found in docs blocks but not in chunks.
        URLs are deduplicated and normalized (trailing slashes stripped for comparison).
        Never raises — handles malformed input gracefully.
    """
    try:
        # Extract all <docs>...</docs> blocks
        docs_pattern = r'<docs>(.*?)</docs>'
        docs_blocks = re.findall(docs_pattern, response_text, re.DOTALL | re.IGNORECASE)

        if not docs_blocks:
            return []

        # Collect all URLs from all docs blocks
        all_doc_urls = []
        for block in docs_blocks:
            # Split by lines and process each line
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    continue

                # Extract URLs from this line
                urls = _extract_urls_from_text(line)
                all_doc_urls.extend(urls)

        if not all_doc_urls:
            return []

        # Deduplicate by normalization
        seen_normalized = set()
        unique_urls = []
        for url in all_doc_urls:
            normalized = _normalize_url(url)
            if normalized and normalized not in seen_normalized:
                seen_normalized.add(normalized)
                unique_urls.append(url)

        # Build set of chunk URLs (normalized)
        chunk_urls_normalized = set()
        if chunks:
            for chunk in chunks:
                if isinstance(chunk, dict) and 'url' in chunk:
                    chunk_url = chunk.get('url')
                    if chunk_url:
                        normalized = _normalize_url(str(chunk_url))
                        chunk_urls_normalized.add(normalized)

        # Find unretrieved URLs
        unretrieved = []
        for url in unique_urls:
            normalized = _normalize_url(url)
            if normalized not in chunk_urls_normalized:
                unretrieved.append(url)

        return unretrieved

    except Exception as exc:
        logging.debug("find_unretrieved_doc_urls exception: %s", exc)
        return []


def _get_cited_doc_urls_count(response_text: str) -> int:
    """Get the count of unique URLs cited in <docs> blocks.

    Used for logging metrics.
    """
    try:
        docs_pattern = r'<docs>(.*?)</docs>'
        docs_blocks = re.findall(docs_pattern, response_text, re.DOTALL | re.IGNORECASE)

        if not docs_blocks:
            return 0

        seen_normalized = set()
        for block in docs_blocks:
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    continue
                urls = _extract_urls_from_text(line)
                for url in urls:
                    normalized = _normalize_url(url)
                    if normalized:
                        seen_normalized.add(normalized)

        return len(seen_normalized)

    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def stream_run(question: str, history: list):
    """Stream a Claude response as a sequence of event dicts.

    Pre-retrieves docs, then streams the completion. Yields one
    {"type": "delta", "text": str} per text chunk, followed by exactly one
    {"type": "done", "response": str, "input_tokens": int, "output_tokens": int,
     "latency_ms": int, "chunks": list[dict]} — chunks are the retrieved doc
    chunks (each {"source", "path", "text", "url"}), for a debug view; [] when RAG
    is not configured or nothing matched.

    Raises RuntimeError if the model returns no text, or stops for any
    reason other than end_turn (e.g. max_tokens truncation).
    """
    start = time.time()

    # Pre-retrieve docs before calling Claude: embed the question, search Qdrant,
    # and inject the context into the user message so one Claude call is enough.
    context = ""
    chunks: list = []
    if retrieval._qdrant is not None and retrieval._voyage is not None:
        try:
            context, chunks = retrieval.retrieve_context_and_chunks(question)
        except Exception as exc:
            logging.warning("pre-retrieval failed: %s", exc)

    messages = build_messages(question, history, context=context)

    full_text = ""
    with _client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        for delta in stream.text_stream:
            full_text += delta
            yield {"type": "delta", "text": delta}
        final_message = stream.get_final_message()

    if not full_text:
        raise RuntimeError("No text in model response")

    if final_message.stop_reason != "end_turn":
        raise RuntimeError(f"Unexpected stop_reason: {final_message.stop_reason}")

    # Check for unretrieved doc URLs and log if any found
    unretrieved_urls = find_unretrieved_doc_urls(full_text, chunks)
    if unretrieved_urls:
        n_cited = _get_cited_doc_urls_count(full_text)
        logging.warning(
            "docs-url-miss n_unretrieved=%d n_cited=%d urls=%s",
            len(unretrieved_urls),
            n_cited,
            unretrieved_urls,
        )

    yield {
        "type": "done",
        "response": full_text,
        "input_tokens": final_message.usage.input_tokens,
        "output_tokens": final_message.usage.output_tokens,
        "latency_ms": round((time.time() - start) * 1000),
        "chunks": chunks,
    }
