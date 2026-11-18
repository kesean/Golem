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

# An unclosed <docs> runs to the end of the text, so everything after it is filtered too.
_DOCS_BLOCK_RE = re.compile(r"<docs\s*>(.*?)(?:</docs\s*>|\Z)", re.DOTALL | re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TITLE_MAX_CHARS = 100


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


def _url_key(url: str) -> str:
    """Scheme, host and path, lower-cased. Query and fragment do not identify a document."""
    parts = urlsplit(_norm_url(url))
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/").lower()


def _retrieved_map(chunks: list[dict] | None) -> dict[str, str]:
    """url key -> canonical retrieved URL, as the retrieval layer produced it."""
    found: dict[str, str] = {}
    for chunk in chunks or []:
        if isinstance(chunk, dict) and chunk.get("url"):
            canonical = _norm_url(str(chunk["url"]))
            found.setdefault(_url_key(canonical), canonical)
    return found


def find_unretrieved_doc_urls(response_text: str, chunks: list[dict] | None) -> list[str]:
    """<docs> URLs that are not the url of any retrieved chunk. Never raises."""
    try:
        retrieved = _retrieved_map(chunks)
        return [u for u in _cited_doc_urls(response_text) if _url_key(u) not in retrieved]
    except Exception as exc:
        logging.debug("find_unretrieved_doc_urls failed: %s", exc)
        return []


def _clean_title(text: str) -> str:
    """Plain text for a citation title: no angle brackets, no line breaks, capped length."""
    text = re.sub(r"[<>]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_TITLE_MAX_CHARS].strip()


def filter_docs_block(response_text: str, chunks: list[dict] | None) -> str:
    """Rebuild each <docs> line as "<sanitised title>: <retrieved canonical URL>", or drop it.

    A line survives only if it holds exactly one http(s) URL and that URL's
    scheme, host and path match a retrieved chunk. Query strings and fragments
    are ignored for matching, and the output uses the retrieved URL, so the
    model's own title and URL text never reach the client verbatim. Blank lines
    are layout and stay. Lines with no URL, a javascript: link or a bare domain
    are dropped. Fails closed: on any error every docs line is dropped.
    """
    try:
        retrieved = _retrieved_map(chunks)

        def rebuild(line: str) -> str | None:
            if not line.strip():
                return line
            urls = _URL_RE.findall(line)
            if len(urls) != 1:
                return None
            canonical = retrieved.get(_url_key(urls[0]))
            if canonical is None:
                return None
            title = _clean_title(line[: line.index(urls[0])].strip().rstrip(":"))
            return f"{title}: {canonical}" if title else canonical

        def rewrite(match: re.Match) -> str:
            kept = [out for out in map(rebuild, match.group(1).split("\n")) if out is not None]
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
