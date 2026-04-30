"""test_prompt.py — Unit tests for prompt.build_messages."""

from prompt import build_messages, SYSTEM_PROMPT


def test_user_message_is_wrapped_in_delimiters():
    result = build_messages("Why am I getting a 401?")
    assert result == [{"role": "user", "content": "<user_input>\nWhy am I getting a 401?\n</user_input>"}]


def test_history_is_prepended_before_user_message():
    history = [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
    ]
    result = build_messages("Second question", history=history)
    assert len(result) == 3
    assert result[0] == {"role": "user", "content": "First question"}
    assert result[1] == {"role": "assistant", "content": "First answer"}
    assert result[2] == {"role": "user", "content": "<user_input>\nSecond question\n</user_input>"}


def test_none_history_treated_as_empty():
    result = build_messages("Hello", history=None)
    assert result == [{"role": "user", "content": "<user_input>\nHello\n</user_input>"}]


def test_empty_history_treated_as_empty():
    result = build_messages("Hello", history=[])
    assert result == [{"role": "user", "content": "<user_input>\nHello\n</user_input>"}]


def test_original_history_list_is_not_mutated():
    history = [{"role": "user", "content": "q"}]
    build_messages("new question", history=history)
    assert len(history) == 1


def test_context_appended_outside_delimiters():
    context = "--- RETRIEVED DOCS ---\nsome doc\n--- END DOCS ---"
    result = build_messages("Why a 401?", context=context)
    assert result == [{"role": "user", "content": "<user_input>\nWhy a 401?\n</user_input>\n\n" + context}]


def test_empty_context_leaves_message_with_delimiters_only():
    result = build_messages("Hello", context="")
    assert result == [{"role": "user", "content": "<user_input>\nHello\n</user_input>"}]


def test_system_prompt_contains_injection_defense():
    assert "must always respond in the XML format" in SYSTEM_PROMPT
    assert "ignore" in SYSTEM_PROMPT.lower()
