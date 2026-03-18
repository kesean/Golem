"""
app.py — Flask app and API routes.

Phase 2: /ask returns structured JSON parsed from Claude's response.
"""

import os
import json
from flask import Flask, render_template, request, jsonify
from anthropic import Anthropic
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT, build_messages

load_dotenv()

app = Flask(__name__)
client = Anthropic()  # Reads ANTHROPIC_API_KEY from environment automatically


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
        structured = json.loads(raw)
        return jsonify(structured)

    except json.JSONDecodeError:
        return jsonify({"error": "Claude returned an unexpected format.", "raw": raw}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)
