"""test_chat.py — Unit tests for chat.py."""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream_cm(deltas, input_tokens=10, output_tokens=20):
    """Build a mock for _client.messages.stream(...)'s context manager.

    deltas: list of text chunks yielded by stream.text_stream.
    """
    final_message = MagicMock()
    final_message.usage.input_tokens = input_tokens
    final_message.usage.output_tokens = output_tokens

    stream = MagicMock()
    stream.text_stream = iter(deltas)
    stream.get_final_message.return_value = final_message

    cm = MagicMock()
    cm.__enter__.return_value = stream
    cm.__exit__.return_value = False
    return cm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_deltas_then_done_event():
    """Text deltas stream first, followed by exactly one done event."""
    import chat

    cm = _make_stream_cm(["<summary>", "Test", "</summary>"], input_tokens=10, output_tokens=20)

    with patch.object(chat._client.messages, "stream", return_value=cm):
        events = list(chat.stream_run("What is JWT?", []))

    assert events[:3] == [
        {"type": "delta", "text": "<summary>"},
        {"type": "delta", "text": "Test"},
        {"type": "delta", "text": "</summary>"},
    ]
    assert len(events) == 4
    done = events[3]
    assert done["type"] == "done"
    assert done["response"] == "<summary>Test</summary>"
    assert done["input_tokens"] == 10
    assert done["output_tokens"] == 20
    assert isinstance(done["latency_ms"], (int, float))
    assert done["latency_ms"] >= 0
    assert done["chunks"] == []


def test_pre_retrieval_context_and_chunks_injected():
    """retrieve_context_and_chunks called with the question; context goes in the
    prompt and chunks ride along on the done event for the debug panel."""
    import chat
    import retrieval as retrieval_module

    cm = _make_stream_cm(["<summary>Answer with context</summary>"])
    fake_chunks = [{"source": "Clerk", "path": "docs/sessions.mdx", "text": "Session info."}]

    with patch.object(chat._client.messages, "stream", return_value=cm) as mock_stream:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(
                    retrieval_module, "retrieve_context_and_chunks",
                    return_value=("clerk docs", fake_chunks),
                ) as mock_rc:
                    events = list(chat.stream_run("How does JWT auth work?", []))

    mock_rc.assert_called_once_with("How does JWT auth work?")
    user_content = mock_stream.call_args[1]["messages"][-1]["content"]
    assert "clerk docs" in user_content
    done = events[-1]
    assert done["response"] == "<summary>Answer with context</summary>"
    assert done["chunks"] == fake_chunks


def test_pre_retrieval_failure_still_answers():
    """retrieve_context_and_chunks raises — Claude is still called, without
    context, and the done event carries an empty chunks list."""
    import chat
    import retrieval as retrieval_module

    cm = _make_stream_cm(["<summary>Recovered answer</summary>"])

    with patch.object(chat._client.messages, "stream", return_value=cm) as mock_stream:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(
                    retrieval_module, "retrieve_context_and_chunks",
                    side_effect=Exception("Qdrant down"),
                ):
                    events = list(chat.stream_run("Some question", []))

    done = events[-1]
    assert done["response"] == "<summary>Recovered answer</summary>"
    assert done["chunks"] == []
    assert "RETRIEVED DOCS" not in mock_stream.call_args[1]["messages"][-1]["content"]


def test_uses_current_model_and_no_tools():
    """Exactly one Claude stream call, using chat.MODEL, with no tools."""
    import chat

    cm = _make_stream_cm(["ok"])

    with patch.object(chat._client.messages, "stream", return_value=cm) as mock_stream:
        list(chat.stream_run("Question", []))

    mock_stream.assert_called_once()
    assert mock_stream.call_args[1]["model"] == chat.MODEL == "claude-sonnet-5"
    assert "tools" not in mock_stream.call_args[1]


def test_no_text_raises():
    """No deltas at all raises RuntimeError, and no done event is yielded."""
    import chat

    cm = _make_stream_cm([])

    with patch.object(chat._client.messages, "stream", return_value=cm):
        with pytest.raises(RuntimeError, match="No text in model response"):
            list(chat.stream_run("Question", []))
