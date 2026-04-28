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

_RETRIEVE_DOCS_TOOL = {
    "name": "retrieve_docs",
    "description": (
        "Search embedded documentation for relevant context. "
        "Use when the question is about Clerk auth, JWT, MDN web APIs, "
        "or general developer concepts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "source": {
                "type": ["string", "null"],
                "enum": ["clerk", "mdn", None],
                "description": "Filter to a specific doc source, or null to search all.",
            },
        },
        "required": ["query"],
    },
}

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

# Only advertise retrieve_docs when RAG backends are actually available.
# Without this guard Claude makes a pointless tool-call round trip on every
# request, doubling latency (~12 s → ~6 s) for zero benefit.
TOOLS = [_API_LOOKUP_TOOL]
if retrieval._qdrant is not None and retrieval._voyage is not None:
    TOOLS.insert(0, _RETRIEVE_DOCS_TOOL)

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
    msgs = build_messages(question, history)

    input_tokens = 0
    output_tokens = 0
    round_count = 0

    while True:
        message = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=msgs,
            tools=TOOLS,
        )

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
    if name == "retrieve_docs":
        try:
            result = retrieval.retrieve_context(inputs["query"], source=inputs.get("source"))
            return result if result else "No docs found."
        except Exception as exc:
            logging.warning("_dispatch_tool: retrieve_docs failed: %s", exc)
            return "No docs found."

    if name == "api_lookup":
        try:
            return api_lookup.fetch(inputs["service"], inputs["endpoint"], inputs.get("params"))
        except Exception as exc:
            logging.warning("_dispatch_tool: api_lookup failed: %s", exc)
            return f"Error: api_lookup failed — {exc}"

    logging.warning("_dispatch_tool: unknown tool name '%s'", name)
    return "Error: unknown tool."
