"""test_chat.py — Unit tests for chat.py."""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stream_cm(deltas, input_tokens=10, output_tokens=20, stop_reason="end_turn"):
    """Build a mock for _client.messages.stream(...)'s context manager.

    deltas: list of text chunks yielded by stream.text_stream.
    """
    final_message = MagicMock()
    final_message.usage.input_tokens = input_tokens
    final_message.usage.output_tokens = output_tokens
    final_message.stop_reason = stop_reason

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


def test_pre_retrieval_context_injected():
    """retrieve_context called with the full question before Claude when clients are available."""
    import chat
    import retrieval as retrieval_module

    cm = _make_stream_cm(["<summary>Answer with context</summary>"])

    with patch.object(chat._client.messages, "stream", return_value=cm) as mock_stream:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(retrieval_module, "retrieve_context", return_value="clerk docs") as mock_rc:
                    events = list(chat.stream_run("How does JWT auth work?", []))

    mock_rc.assert_called_once_with("How does JWT auth work?")
    user_content = mock_stream.call_args[1]["messages"][-1]["content"]
    assert "clerk docs" in user_content
    assert events[-1]["response"] == "<summary>Answer with context</summary>"


def test_pre_retrieval_failure_still_answers():
    """retrieve_context raises — Claude is still called, without context."""
    import chat
    import retrieval as retrieval_module

    cm = _make_stream_cm(["<summary>Recovered answer</summary>"])

    with patch.object(chat._client.messages, "stream", return_value=cm) as mock_stream:
        with patch.object(retrieval_module, "_qdrant", MagicMock()):
            with patch.object(retrieval_module, "_voyage", MagicMock()):
                with patch.object(retrieval_module, "retrieve_context", side_effect=Exception("Qdrant down")):
                    events = list(chat.stream_run("Some question", []))

    assert events[-1]["response"] == "<summary>Recovered answer</summary>"
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


def test_max_tokens_truncation_raises():
    """stop_reason == 'max_tokens' raises instead of yielding a done event for a
    truncated response — even though deltas already streamed to the client,
    app.py turns this into an 'error' SSE event instead of 'done'."""
    import chat

    cm = _make_stream_cm(["<summary>cut off halfway"], stop_reason="max_tokens")

    with patch.object(chat._client.messages, "stream", return_value=cm):
        events = []
        with pytest.raises(RuntimeError, match="Unexpected stop_reason: max_tokens"):
            for event in chat.stream_run("Question", []):
                events.append(event)

    # The partial delta was already yielded before the truncation was detected
    assert events == [{"type": "delta", "text": "<summary>cut off halfway"}]
