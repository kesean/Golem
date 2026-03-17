"""
prompt.py — System prompt and message-building logic.

This is where you'll do most of your prompt engineering work in Phase 2.
For now (Phase 1), it's a simple system prompt that gets the basics working.
"""

SYSTEM_PROMPT = """You are a knowledgeable developer support engineer. \
Your job is to help developers debug issues, understand error messages, \
and find solutions quickly.

When answering a question:
- Be concise and direct
- Lead with the most likely cause or solution
- Include a short code example if it helps
- If you're unsure, say so — don't invent answers

Tone: helpful, technically precise, no fluff.
"""


def build_messages(user_question: str) -> list[dict]:
    """
    Build the messages array for the Claude API call.

    In Phase 2 you'll expand this to:
    - Include conversation history for follow-up questions
    - Add structured output instructions
    - Tag by product area (API, SDK, webhooks, etc.)
    """
    return [
        {"role": "user", "content": user_question}
    ]
