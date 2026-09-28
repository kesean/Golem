"""test_chat.py — Unit tests for chat.py."""

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


def test_pre_retrieval_context_injected():
    """retrieve_context called with the full question before Claude when clients are available."""
    import chat
    import retrieval as retrieval_module

    end_msg = _make_end_turn_msg(text="<summary>Answer with context</summary>")

    with patch.object(chat._client.messages, "create", return_value=end_msg) as mock_create:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(retrieval_module, "retrieve_context", return_value="clerk docs") as mock_rc:
                    result = chat.run("How does JWT auth work?", [])

    mock_rc.assert_called_once_with("How does JWT auth work?")
    user_content = mock_create.call_args[1]["messages"][-1]["content"]
    assert "clerk docs" in user_content
    assert result["response"] == "<summary>Answer with context</summary>"


def test_pre_retrieval_failure_still_answers():
    """retrieve_context raises — Claude is still called, without context."""
    import chat
    import retrieval as retrieval_module

    end_msg = _make_end_turn_msg(text="<summary>Recovered answer</summary>")

    with patch.object(chat._client.messages, "create", return_value=end_msg) as mock_create:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(retrieval_module, "retrieve_context", side_effect=Exception("Qdrant down")):
                    result = chat.run("Some question", [])

    assert result["response"] == "<summary>Recovered answer</summary>"
    assert "RETRIEVED DOCS" not in mock_create.call_args[1]["messages"][-1]["content"]


def test_uses_current_model_and_single_call():
    """Exactly one Claude call, using chat.MODEL, with no tools."""
    import chat

    end_msg = _make_end_turn_msg()

    with patch.object(chat._client.messages, "create", return_value=end_msg) as mock_create:
        chat.run("Question", [])

    mock_create.assert_called_once()
    assert mock_create.call_args[1]["model"] == chat.MODEL == "claude-sonnet-5"
    assert "tools" not in mock_create.call_args[1]


def test_no_text_block_raises():
    """end_turn response with no text block raises RuntimeError."""
    import chat

    msg = MagicMock()
    msg.stop_reason = "end_turn"
    msg.content = []
    msg.usage.input_tokens = 1
    msg.usage.output_tokens = 1

    with patch.object(chat._client.messages, "create", return_value=msg):
        with pytest.raises(RuntimeError, match="No text in model response"):
            chat.run("Question", [])


def test_max_tokens_truncation_raises():
    """stop_reason == 'max_tokens' raises instead of returning a truncated answer."""
    import chat

    msg = _make_end_turn_msg(text="<summary>cut off halfway")
    msg.stop_reason = "max_tokens"

    with patch.object(chat._client.messages, "create", return_value=msg):
        with pytest.raises(RuntimeError, match="Unexpected stop_reason: max_tokens"):
            chat.run("Question", [])
