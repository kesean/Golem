"""
chat.py — Claude call orchestrator.

Exposes run(question, history) -> dict.
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

def run(question: str, history: list) -> dict:
    """Pre-retrieve docs, then make a single Claude call.

    Returns { response, input_tokens, output_tokens, latency_ms }.
    Raises RuntimeError if the model returns no text, or stops for any
    reason other than end_turn (e.g. max_tokens truncation).
    """
    start = time.time()

    # Pre-retrieve docs before calling Claude: embed the question, search Qdrant,
    # and inject the context into the user message so one Claude call is enough.
    context = ""
    if retrieval._qdrant is not None and retrieval._voyage is not None:
        try:
            context = retrieval.retrieve_context(question)
        except Exception as exc:
            logging.warning("pre-retrieval failed: %s", exc)

    message = _client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=build_messages(question, history, context=context),
    )

    if message.stop_reason != "end_turn":
        raise RuntimeError(f"Unexpected stop_reason: {message.stop_reason}")

    text_block = next((b for b in message.content if b.type == "text"), None)
    if not text_block:
        raise RuntimeError("No text in model response")

    return {
        "response": text_block.text,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "latency_ms": round((time.time() - start) * 1000),
    }
