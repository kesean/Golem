"""test_chat.py — Unit tests for chat.py tool loop orchestrator."""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_end_turn_msg(text="<summary>Test</summary>", input_tokens=10, output_tokens=20):
    """Build a mock end_turn response."""
    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = [MagicMock(text=text, type="text")]
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg


def _make_tool_use_msg(tool_calls, input_tokens=10, output_tokens=5):
    """Build a mock tool_use response with one or more tool_call blocks.

    tool_calls: list of dicts with keys: name, id, input
    """
    blocks = []
    for tc in tool_calls:
        block = MagicMock()
        block.type = "tool_use"
        block.id = tc["id"]
        block.name = tc["name"]
        block.input = tc["input"]
        blocks.append(block)

    msg = MagicMock()
    msg.stop_reason = "tool_use"
    msg.content = blocks
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_tool_call_returns_answer_directly():
    """Single end_turn response returns correct dict shape."""
    import chat

    end_msg = _make_end_turn_msg(text="<summary>Direct answer</summary>", input_tokens=10, output_tokens=20)

    with patch.object(chat._client.messages, "create", return_value=end_msg):
        result = chat.run("What is JWT?", [])

    assert result["response"] == "<summary>Direct answer</summary>"
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 20
    assert isinstance(result["latency_ms"], (int, float))
    assert result["latency_ms"] >= 0


def test_retrieve_docs_tool_call_dispatched():
    """retrieve_docs tool_use followed by end_turn — retrieve_context called with correct args."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_001", "name": "retrieve_docs", "input": {"query": "JWT auth", "source": "clerk"}},
    ])
    end_msg = _make_end_turn_msg(text="<summary>Final answer</summary>")

    with patch.object(chat._client.messages, "create", side_effect=[tool_msg, end_msg]):
        with patch("chat.retrieval.retrieve_context", return_value="clerk docs context") as mock_rc:
            result = chat.run("How does JWT auth work?", [])

    mock_rc.assert_called_once_with("JWT auth", source="clerk")
    assert result["response"] == "<summary>Final answer</summary>"


def test_api_lookup_tool_call_dispatched():
    """api_lookup tool_use followed by end_turn — api_lookup.fetch called with correct args."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_002", "name": "api_lookup", "input": {"service": "anthropic", "endpoint": "models", "params": None}},
    ])
    end_msg = _make_end_turn_msg(text="<summary>Models answer</summary>")

    with patch.object(chat._client.messages, "create", side_effect=[tool_msg, end_msg]):
        with patch("chat.api_lookup.fetch", return_value='{"models": []}') as mock_fetch:
            result = chat.run("What models are available?", [])

    mock_fetch.assert_called_once_with("anthropic", "models", None)
    assert result["response"] == "<summary>Models answer</summary>"


def test_both_tools_called_in_same_turn():
    """Single response with two tool_use blocks — both dispatched."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_003", "name": "retrieve_docs", "input": {"query": "CORS headers"}},
        {"id": "tool_004", "name": "api_lookup", "input": {"service": "clerk", "endpoint": "errors"}},
    ])
    end_msg = _make_end_turn_msg(text="<summary>Combined answer</summary>")

    with patch.object(chat._client.messages, "create", side_effect=[tool_msg, end_msg]):
        with patch("chat.retrieval.retrieve_context", return_value="docs") as mock_rc:
            with patch("chat.api_lookup.fetch", return_value="errors data") as mock_fetch:
                result = chat.run("CORS and Clerk errors", [])

    mock_rc.assert_called_once_with("CORS headers", source=None)
    mock_fetch.assert_called_once_with("clerk", "errors", None)
    assert result["response"] == "<summary>Combined answer</summary>"


def test_tool_failure_returns_error_string_loop_continues():
    """retrieve_context raises — loop continues and returns final answer without raising."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_005", "name": "retrieve_docs", "input": {"query": "broken query"}},
    ])
    end_msg = _make_end_turn_msg(text="<summary>Recovered answer</summary>")

    with patch.object(chat._client.messages, "create", side_effect=[tool_msg, end_msg]):
        with patch("chat.retrieval.retrieve_context", side_effect=Exception("Qdrant down")):
            result = chat.run("Some question", [])

    # Should not raise; the loop should send an error string as tool result and continue
    assert result["response"] == "<summary>Recovered answer</summary>"


def test_max_tool_rounds_exceeded_raises():
    """Always returns tool_use — RuntimeError after MAX_TOOL_ROUNDS."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_006", "name": "retrieve_docs", "input": {"query": "infinite loop query"}},
    ])

    with patch.object(chat._client.messages, "create", return_value=tool_msg):
        with patch("chat.retrieval.retrieve_context", return_value="some docs"):
            with pytest.raises(RuntimeError, match="tool loop exceeded MAX_TOOL_ROUNDS"):
                chat.run("Infinite tool loop", [])


def test_unknown_tool_name_returns_error_string():
    """tool_use block with unknown name — loop continues with error string result."""
    import chat

    tool_msg = _make_tool_use_msg([
        {"id": "tool_007", "name": "nonexistent_tool", "input": {"foo": "bar"}},
    ])
    end_msg = _make_end_turn_msg(text="<summary>Answer after unknown tool</summary>")

    with patch.object(chat._client.messages, "create", side_effect=[tool_msg, end_msg]):
        result = chat.run("Question triggering unknown tool", [])

    assert result["response"] == "<summary>Answer after unknown tool</summary>"
