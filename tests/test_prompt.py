"""test_prompt.py — Unit tests for prompt.build_messages."""

from prompt import build_messages


def test_no_history_returns_single_user_message():
    result = build_messages("Why am I getting a 401?")
    assert result == [{"role": "user", "content": "Why am I getting a 401?"}]


def test_history_is_prepended_before_user_message():
    history = [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
    ]
    result = build_messages("Second question", history=history)
    assert len(result) == 3
    assert result[0] == {"role": "user", "content": "First question"}
    assert result[1] == {"role": "assistant", "content": "First answer"}
    assert result[2] == {"role": "user", "content": "Second question"}


def test_none_history_treated_as_empty():
    result = build_messages("Hello", history=None)
    assert result == [{"role": "user", "content": "Hello"}]


def test_empty_history_treated_as_empty():
    result = build_messages("Hello", history=[])
    assert result == [{"role": "user", "content": "Hello"}]


def test_original_history_list_is_not_mutated():
    history = [{"role": "user", "content": "q"}]
    build_messages("new question", history=history)
    assert len(history) == 1  # build_messages must not append to the caller's list


def test_build_messages_no_context_no_history():
    """No context, no history — produces a single user turn."""
    messages = build_messages("Why am I getting a 401?")
    assert messages == [{"role": "user", "content": "Why am I getting a 401?"}]


def test_build_messages_no_context_with_history():
    """No context — history + new question, content unchanged."""
    history = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    messages = build_messages("Follow-up?", history)
    assert len(messages) == 3
    assert messages[-1] == {"role": "user", "content": "Follow-up?"}


