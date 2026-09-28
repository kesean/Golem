"""
chat.py — Claude call orchestrator.

Exposes stream_run(question, history) -> generator of SSE-ready event dicts.
"""

import logging
import os
import time

import anthropic

import retrieval
from prompt import SYSTEM_PROMPT, build_messages

# ---------------------------------------------------------------------------
# Anthropic client — initialized once at module level
# ---------------------------------------------------------------------------

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

MODEL = "claude-sonnet-5"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def stream_run(question: str, history: list):
    """Stream a Claude response as a sequence of event dicts.

    Pre-retrieves docs, then streams the completion. Yields one
    {"type": "delta", "text": str} per text chunk, followed by exactly one
    {"type": "done", "response": str, "input_tokens": int, "output_tokens": int,
     "latency_ms": int, "chunks": list[dict]} — chunks are the retrieved doc
    chunks (each {"source", "path", "text"}), for a debug view; [] when RAG
    is not configured or nothing matched.

    Raises RuntimeError if the model returns no text.
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

    yield {
        "type": "done",
        "response": full_text,
        "input_tokens": final_message.usage.input_tokens,
        "output_tokens": final_message.usage.output_tokens,
        "latency_ms": round((time.time() - start) * 1000),
        "chunks": chunks,
    }
