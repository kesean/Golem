# Dev Support AI Chatbot

## Project Overview
A developer support chatbot that uses the Claude API to answer technical questions
in a structured, helpful way — similar to how a developer support engineer would respond.

Built with: Python 3 · Flask · Anthropic Python SDK · Vanilla JS frontend

## Goals
- Learn Claude Code workflows
- Practice prompt engineering with real API calls
- Build a portfolio-ready AI project (relevant to developer support roles)

## Project Structure
```
dev-support-chatbot/
├── app.py              # Flask app + API routes
├── prompt.py           # System prompt and prompt-building logic (Phase 2)
├── requirements.txt    # Python dependencies
├── CLAUDE.md           # This file
├── .env                # API key (never commit this)
├── templates/
│   └── index.html      # Main UI
└── static/
    ├── css/style.css
    └── js/app.js       # Frontend JS (fetch calls, streaming in Phase 3)
```

## Development Guidelines
- Keep Flask routes thin — business logic goes in separate modules
- System prompt lives in `prompt.py`, not inline in routes
- Use `python-dotenv` to load `.env` — never hardcode API keys
- Prefer readable code over clever code — this is a learning project
- Keep commit messages short and direct.
- Break each step down into a User story. Review the user story with the User. Then create Git commit and push to GitHub only after getting user approval. 

## Important Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server
python app.py

# App runs at http://localhost:5000
```

## Phases
- **Phase 1**: Basic Flask app, simple API call, raw response displayed
- **Phase 2**: Structured output (Summary / Root Cause / Debug Steps / Docs)
- **Phase 3**: Streaming responses, conversation history, product area tags

## API Notes
- Model: `claude-sonnet-4-6`
- Max tokens: 1024 for Phase 1, increase in later phases
- API key loaded from `.env` as `ANTHROPIC_API_KEY`
