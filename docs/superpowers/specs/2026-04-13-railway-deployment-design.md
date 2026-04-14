# Railway Deployment Design

**Date:** 2026-04-13  
**Scope:** Deploy Flask backend to Railway using GitHub integration + Procfile

---

## Overview

Deploy the Flask backend (`app.py`) to Railway. The frontend (`frontend/`) is excluded — it deploys to Vercel separately. This spec covers only the Railway side.

Two files are added to the repo. Everything else is configured in the Railway dashboard.

---

## Files to Add / Modify

### `Procfile` (new, repo root)

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

- Railway injects `$PORT` at runtime; the app must bind to it.
- The `if __name__ == "__main__":` block in `app.py` is bypassed by gunicorn — `debug=True` and `port=5001` do not apply in production.
- No changes to `app.py`.

### `requirements.txt` (add one line)

```
gunicorn>=21.0.0
```

---

## Railway Dashboard Setup

Performed once after code is merged to `main`.

### 1. Create project

- New Project → Deploy from GitHub repo → select `dev-support-chatbot`
- Root directory: `/` (default)
- Railway auto-deploys on every push to `main` going forward.

### 2. Add Redis plugin

- Add a new service → select Redis
- Railway automatically injects `REDIS_URL` into the Flask service environment — no manual action needed.
- If Redis is not connected, Flask-Limiter silently falls back to `memory://` (no error). Confirm via build logs.

### 3. Set environment variables (Flask service)

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `CLERK_JWKS_URL` | Clerk JWKS URL |
| `FRONTEND_ORIGIN` | Placeholder — update after Vercel deploy |
| `REDIS_URL` | Auto-set by Redis plugin |

`FRONTEND_ORIGIN` left as placeholder until Vercel URL is known. The CORS config in `app.py` handles a missing or empty value by blocking all origins — safe until the frontend URL is available.

---

## Validation

### 1. Server health check

```bash
curl -X POST https://<railway-url>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

Expected: `401 Unauthorized` — confirms the server is up and auth middleware is enforcing.

### 2. Redis connection check

Inspect Railway build logs for a successful Redis connection line. A missing connection means Flask-Limiter is running in-memory (rate limits won't persist across restarts).

---

## What Is Not In Scope

- Vercel frontend deployment (separate spec)
- Custom domain configuration
- CI/CD beyond Railway's built-in GitHub auto-deploy
