# Dev Support AI Chatbot

## Project Overview
A developer support chatbot that uses the Claude API to answer technical questions
in a structured, helpful way — similar to how a developer support engineer would respond.

Built with: Python 3 · Flask · Anthropic Python SDK · Clerk · Convex · Vite · Vanilla JS

## Goals
- Learn Claude Code workflows
- Practice prompt engineering with real API calls
- Build a portfolio-ready AI project (relevant to developer support roles)

## Project Structure
```
dev-support-chatbot/
├── app.py              # Flask app + API routes (JWT auth, rate limiting, streaming)
├── prompt.py           # System prompt and message-building logic
├── requirements.txt    # Python dependencies
├── CLAUDE.md           # This file
├── .env                # API keys for Flask (never commit this)
└── frontend/
    ├── index.html
    ├── vite.config.js
    ├── package.json
    ├── .env            # Frontend env vars (VITE_CLERK_PUBLISHABLE_KEY, VITE_CONVEX_URL)
    ├── convex/         # Convex schema + functions (history table)
    └── src/
        ├── main.js     # Clerk + Convex init, auth wall
        ├── app.js      # Chat UI logic, streaming, history
        └── style.css
```

## Development Guidelines
- Keep Flask routes thin — business logic goes in separate modules
- System prompt lives in `prompt.py`, not inline in routes
- Use `python-dotenv` to load `.env` — never hardcode API keys
- Prefer readable code over clever code — this is a learning project
- Keep commit messages short and direct
- Break each step down into a User story. Review the user story with the User. Then create Git commit and push to GitHub only after getting user approval

## Important Commands
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run Flask dev server (port 5001)
python app.py

# Run Vite frontend (port 5173) — from frontend/
cd frontend && npm install && npm run dev

# Run Convex dev server — from frontend/
cd frontend && npx convex dev
```

## API Notes
- Model: `claude-sonnet-4-6`
- Max tokens: 2048
- API key loaded from `.env` as `ANTHROPIC_API_KEY`

## Auth & Security
- Clerk handles sign-in/sign-up (JWT issued to frontend)
- Flask verifies Clerk JWTs on every `/ask/stream` request via RS256 + JWKS
- Rate limiting via Flask-Limiter:
  - 20 req/min per IP (existing)
  - 10 req/user/day per Clerk user ID (Phase 8)
  - 70 req/day global hard cap (Phase 8)
- Rate limit counters stored in Redis for persistence across deploys (Phase 8)

## Deployment (Phase 8)
- Frontend → Vercel (Vite static build)
- Flask backend → Railway (with Redis add-on)
- Convex → managed cloud (already handled by Convex platform)
- Env vars set in Railway dashboard (never in code)
