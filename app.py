"""
app.py — Flask app and API routes.

Phase 2: /ask returns structured JSON parsed from Claude's response.
Phase 3: /ask/stream streams raw text chunks, frontend parses JSON on completion.
"""

import os
import re
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from anthropic import Anthropic
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT, build_messages

load_dotenv()

app = Flask(__name__)
client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment automatically


def parse_xml_response(text: str) -> dict:
    """Parse the XML-tagged response from Claude into a structured dict."""
    def extract(tag):
        match = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
        return match.group(1).strip() if match else ""

    debug_raw = extract('debug_steps')
    debug_steps = [
        re.sub(r'^Step\s*\d+:\s*', '', line).strip()
        for line in debug_raw.splitlines()
        if line.strip()
    ]

    docs_raw = extract('docs')
    docs = [line.strip() for line in docs_raw.splitlines() if line.strip()]

    return {
        "summary": extract('summary'),
        "root_cause": extract('root_cause'),
        "debug_steps": debug_steps,
        "docs": docs,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    """
    Accepts a JSON body: { "question": "..." }
    Returns:            { "answer": "..." }

    Phase 2: will return structured JSON with Summary, Root Cause, etc.
    Phase 3: will switch to a streaming response.
    """
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=build_messages(question),
        )

        raw = response.content[0].text
        return jsonify(parse_xml_response(raw))

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ask/stream", methods=["POST"])
def ask_stream():
    """
    Accepts a JSON body: { "question": "..." }
    Streams raw text chunks from Claude as text/plain.
    Frontend accumulates chunks, then parses the JSON and renders structured sections.
    """
    data = request.get_json()
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    def generate():
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=build_messages(question),
        ) as stream:
            for text in stream.text_stream:
                yield text

    return Response(stream_with_context(generate()), content_type="text/plain; charset=utf-8")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
