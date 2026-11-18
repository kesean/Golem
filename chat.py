"""
chat.py — Claude call orchestrator.

Exposes stream_run(question, history) -> generator of SSE-ready event dicts.
"""

import logging
import os
import re
import time
from urllib.parse import urlsplit

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

_DOCS_BLOCK_RE = re.compile(r"<docs>(.*?)</docs>", re.DOTALL | re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)


def _norm_url(url: str) -> str:
    return url.rstrip(".,;:!?*`/")


def _loggable(url: str) -> str:
    """scheme://host/path only: user-pasted URLs may carry tokens in query/fragment."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _cited_doc_urls(response_text: str) -> list[str]:
    """Unique http(s) URLs inside <docs> blocks (trailing slash/punctuation stripped), in order."""
    urls = [
        _norm_url(m)
        for block in _DOCS_BLOCK_RE.findall(response_text or "")
        for m in _URL_RE.findall(block)
    ]
    return list(dict.fromkeys(u for u in urls if u))


def _retrieved_urls(chunks: list[dict] | None) -> set[str]:
    return {_norm_url(str(c["url"])).lower() for c in chunks or [] if isinstance(c, dict) and c.get("url")}


def find_unretrieved_doc_urls(response_text: str, chunks: list[dict] | None) -> list[str]:
    """<docs> URLs that are not the url of any retrieved chunk. Never raises."""
    try:
        retrieved = _retrieved_urls(chunks)
        return [u for u in _cited_doc_urls(response_text) if u.lower() not in retrieved]
    except Exception as exc:
        logging.debug("find_unretrieved_doc_urls failed: %s", exc)
        return []


def filter_docs_block(response_text: str, chunks: list[dict] | None) -> str:
    """Keep a <docs> line only if it cites at least one URL and every URL on it was retrieved.

    The whole line goes, not just the URL, because the title on it can carry
    the payload too. Lines with no http(s) URL are dropped as well: the
    allowlist is what was retrieved, not what a denylist misses (javascript:
    links, bare domains). Fails closed: on any error every docs line is dropped.
    """
    try:
        retrieved = _retrieved_urls(chunks)

        def keep(line: str) -> bool:
            urls = [_norm_url(u).lower() for u in _URL_RE.findall(line)]
            return bool(urls) and all(u in retrieved for u in urls)

        def rewrite(match: re.Match) -> str:
            # Blank lines are layout and stay; any other line must pass keep().
            kept = [line for line in match.group(1).split("\n") if not line.strip() or keep(line)]
            return "<docs>" + "\n".join(kept) + "</docs>"

        return _DOCS_BLOCK_RE.sub(rewrite, response_text or "")
    except Exception as exc:
        logging.warning("filter_docs_block failed; dropping all docs: %s", exc)
        return _DOCS_BLOCK_RE.sub("<docs></docs>", response_text or "")


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
    try:
        unretrieved_urls = find_unretrieved_doc_urls(full_text, chunks)
        if unretrieved_urls:
            logging.warning(
                "docs-url-miss n_unretrieved=%d n_cited=%d urls=%s",
                len(unretrieved_urls),
                len(_cited_doc_urls(full_text)),
                [_loggable(u) for u in unretrieved_urls],
            )
    except Exception as exc:  # logging must never break the stream
        logging.debug("docs-url-miss logging failed: %s", exc)

    # Deltas already streamed unfiltered; `done.response` is the text clients keep.
    yield {
        "type": "done",
        "response": filter_docs_block(full_text, chunks),
        "input_tokens": final_message.usage.input_tokens,
        "output_tokens": final_message.usage.output_tokens,
        "latency_ms": round((time.time() - start) * 1000),
        "chunks": chunks,
    }
