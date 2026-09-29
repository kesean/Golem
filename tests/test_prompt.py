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


def test_system_prompt_contains_canonical_url_rules():
    """SYSTEM_PROMPT contains new rules about citing only retrieved docs."""
    assert "Title: URL" in SYSTEM_PROMPT
    assert "--- RETRIEVED DOCS ---" in SYSTEM_PROMPT
    assert "never invent" in SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_cite_only_retrieved_docs():
    """SYSTEM_PROMPT mentions citing ONLY retrieved docs."""
    assert "cite ONLY documents" in SYSTEM_PROMPT


def test_system_prompt_references_retrieved_docs_section():
    """SYSTEM_PROMPT references the '--- RETRIEVED DOCS ---' section."""
    assert "--- RETRIEVED DOCS ---" in SYSTEM_PROMPT


def test_system_prompt_specifies_url_line_wording():
    """SYSTEM_PROMPT specifies using URL: line."""
    assert "'URL:' line" in SYSTEM_PROMPT


def test_system_prompt_requires_no_duplicates():
    """SYSTEM_PROMPT requires listing each document once."""
    assert "once" in SYSTEM_PROMPT.lower()
    assert "no duplicates" in SYSTEM_PROMPT.lower()


def test_system_prompt_contains_docs_refusal_block():
    """SYSTEM_PROMPT still contains <docs></docs> in the refusal block."""
    assert "<docs></docs>" in SYSTEM_PROMPT
