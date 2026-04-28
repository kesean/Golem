"""
chat.py — Multi-turn Claude tool loop orchestrator.

Exposes run(question, history) -> dict and internal _dispatch_tool(name, inputs) -> str.
"""

import logging
import os
import time

import anthropic

import api_lookup
import retrieval
from prompt import SYSTEM_PROMPT, build_messages

# ---------------------------------------------------------------------------
# Anthropic client — initialized once at module level
# ---------------------------------------------------------------------------

_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_API_LOOKUP_TOOL = {
    "name": "api_lookup",
    "description": (
        "Fetch live data from the Clerk or Anthropic API. "
        "Use for error codes, JWKS keys, or current model information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "enum": ["clerk", "anthropic"]},
            "endpoint": {"type": "string", "description": "Endpoint key from the allowlist"},
            "params": {"type": ["object", "null"], "description": "Optional query params"},
        },
        "required": ["service", "endpoint"],
    },
}

TOOLS = [_API_LOOKUP_TOOL]

MAX_TOOL_ROUNDS = 3


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run(question: str, history: list) -> dict:
    """Run Claude with tool_use loop.

    Returns { response, input_tokens, output_tokens, latency_ms }.
    Raises RuntimeError if MAX_TOOL_ROUNDS is exceeded or no content is returned.
    """
    start = time.time()

    # Pre-retrieve docs before calling Claude — eliminates a tool-use round trip.
    # retrieve_docs was a tool; now we embed the question and search Qdrant directly,
    # injecting context into the user message instead of making a second Claude call.
    context = ""
    if retrieval._qdrant is not None and retrieval._voyage is not None:
        try:
            context = retrieval.retrieve_context(question)
        except Exception as exc:
            logging.warning("pre-retrieval failed: %s", exc)

    msgs = build_messages(question, history, context=context)

    input_tokens = 0
    output_tokens = 0
    round_count = 0

    while True:
        # Only offer tools on the first call. Claude can call any/all tools
        # it needs in one round (parallel tool use). Subsequent calls have no
        # tools so stop_reason is always end_turn — guarantees 2 API calls max.
        kwargs: dict = dict(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=msgs,
        )
        if round_count == 0 and TOOLS:
            kwargs["tools"] = TOOLS

        message = _client.messages.create(**kwargs)

        input_tokens += message.usage.input_tokens
        output_tokens += message.usage.output_tokens

        if message.stop_reason == "end_turn":
            text_block = next((b for b in message.content if b.type == "text"), None)
            if not text_block:
                raise RuntimeError("No text in model response")
            latency_ms = round((time.time() - start) * 1000)
            return {
                "response": text_block.text,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": latency_ms,
            }

        if message.stop_reason == "tool_use":
            tool_use_blocks = [b for b in message.content if b.type == "tool_use"]
            results = [_dispatch_tool(b.name, b.input) for b in tool_use_blocks]

            # Append assistant message with all content blocks
            msgs.append({"role": "assistant", "content": message.content})

            # Append tool results as a single user message
            msgs.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_string,
                    }
                    for block, result_string in zip(tool_use_blocks, results)
                ],
            })

            round_count += 1
            if round_count >= MAX_TOOL_ROUNDS:
                raise RuntimeError("tool loop exceeded MAX_TOOL_ROUNDS")
            continue  # loop back; skip the fallthrough raise below

        # Unexpected stop_reason — treat as no content
        raise RuntimeError("No response from model")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dispatch_tool(name: str, inputs: dict) -> str:
    """Route a tool call to retrieval or api_lookup.

    Returns string result. Never raises.
    """
    if name == "api_lookup":
        try:
            return api_lookup.fetch(inputs["service"], inputs["endpoint"], inputs.get("params"))
        except Exception as exc:
            logging.warning("_dispatch_tool: api_lookup failed: %s", exc)
            return f"Error: api_lookup failed — {exc}"

    logging.warning("_dispatch_tool: unknown tool name '%s'", name)
    return "Error: unknown tool."
