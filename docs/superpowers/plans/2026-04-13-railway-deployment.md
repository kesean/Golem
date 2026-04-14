# Railway Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Flask backend to Railway via GitHub integration using a Procfile + gunicorn.

**Architecture:** A `Procfile` at the repo root tells Railway to start the app with gunicorn bound to Railway's injected `$PORT`. The Redis plugin on Railway auto-injects `REDIS_URL`, which `app.py` already reads. No changes to application code.

**Tech Stack:** Python · Flask · gunicorn · Railway (GitHub integration + Redis plugin)

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `requirements.txt` | Add gunicorn as a production dependency |
| Create | `Procfile` | Tell Railway how to start the app |

---

### Task 1: Create feature branch

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/phase-8-railway-deployment
```

Expected output:
```
Switched to a new branch 'feature/phase-8-railway-deployment'
```

---

### Task 2: Add gunicorn to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add gunicorn to requirements.txt**

Open `requirements.txt` and add this line at the end:

```
gunicorn>=21.0.0
```

Full file after change:
```
flask>=3.0.0
anthropic>=0.40.0
python-dotenv>=1.0.0
PyJWT>=2.8.0
cryptography>=42.0.0
Flask-Limiter>=3.5.0
Flask-CORS>=4.0.0
redis>=5.0.0
pytest>=8.0.0
pytest-flask>=1.3.0
gunicorn>=21.0.0
```

- [ ] **Step 2: Install gunicorn**

```bash
pip install gunicorn>=21.0.0
```

Expected output ends with:
```
Successfully installed gunicorn-21.x.x
```

---

### Task 3: Create Procfile

**Files:**
- Create: `Procfile` (repo root, no file extension)

- [ ] **Step 1: Create Procfile**

Create a new file named exactly `Procfile` (capital P, no extension) at the repo root with this single line:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT
```

- `app:app` — module name `app`, Flask instance named `app` inside it
- `--bind 0.0.0.0:$PORT` — Railway injects `$PORT`; binding to `0.0.0.0` makes it reachable externally

- [ ] **Step 2: Verify the file exists at the root**

```bash
ls Procfile
```

Expected:
```
Procfile
```

---

### Task 4: Smoke test gunicorn locally

Verify gunicorn can start the app before committing. This catches import errors or misconfigured module paths.

- [ ] **Step 1: Start gunicorn locally**

```bash
PORT=5001 gunicorn app:app --bind 0.0.0.0:$PORT
```

Expected output (last few lines):
```
[INFO] Starting gunicorn 21.x.x
[INFO] Listening at: http://0.0.0.0:5001
[INFO] Worker booting (pid: ...)
[INFO] Booted worker with pid: ...
```

If you see `ModuleNotFoundError` or `Failed to find application`, stop and check that you are running the command from the repo root (where `app.py` lives).

- [ ] **Step 2: Hit the endpoint**

In a second terminal:

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:5001/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

Expected output:
```
401
```

A `401` confirms gunicorn is serving the app and auth middleware is enforcing. Any other response (502, connection refused) means gunicorn didn't start correctly — check the gunicorn terminal output.

- [ ] **Step 3: Stop gunicorn**

Press `Ctrl+C` in the gunicorn terminal.

---

### Task 5: Commit

- [ ] **Step 1: Stage and commit both files**

```bash
git add requirements.txt Procfile
git commit -m "feat: add Procfile and gunicorn for Railway deployment (US-P8-5)"
```

Expected:
```
[feature/phase-8-railway-deployment ...] feat: add Procfile and gunicorn for Railway deployment (US-P8-5)
 2 files changed, 2 insertions(+)
 create mode 100644 Procfile
```

- [ ] **Step 2: Push branch and open PR**

Push the branch to GitHub, open a PR against `main`, and get it merged. Railway auto-deploys on every push to `main`.

> Note: User pushes to remote manually.

---

### Task 6: Railway dashboard setup (manual — after merge to main)

These steps are performed once in the Railway dashboard. No code changes.

- [ ] **Step 1: Create Railway project**

1. Go to [railway.app](https://railway.app) → New Project
2. Select **Deploy from GitHub repo**
3. Select `dev-support-chatbot`
4. Leave root directory as `/` (default)
5. Railway triggers an initial deploy automatically

- [ ] **Step 2: Add Redis plugin**

1. Inside the project, click **+ New Service**
2. Select **Redis**
3. Railway automatically adds `REDIS_URL` to the Flask service's environment — no manual copy needed

- [ ] **Step 3: Set environment variables on the Flask service**

Navigate to the Flask service → **Variables** tab and add:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `CLERK_SECRET_KEY` | Your Clerk secret key |
| `CLERK_JWKS_URL` | Your Clerk JWKS URL (e.g. `https://<your-clerk-domain>/.well-known/jwks.json`) |
| `FRONTEND_ORIGIN` | Leave blank for now — update after Vercel deploy |

`REDIS_URL` is already set by the Redis plugin — do not add it manually.

- [ ] **Step 4: Trigger redeploy**

After adding variables, Railway may redeploy automatically. If not, click **Deploy** manually to pick up the new env vars.

---

### Task 7: Validate Railway deployment

- [ ] **Step 1: Confirm build logs show Redis connected**

In the Railway dashboard, open the Flask service → **Deployments** → latest deploy → **Build Logs**.

Look for a line referencing the Redis URL. If Flask-Limiter connected to Redis, rate-limit counters persist across restarts. If you don't see it, check that `REDIS_URL` was set by the Redis plugin (Variables tab).

- [ ] **Step 2: Health check against the live URL**

Get your Railway URL from the Flask service → **Settings** → **Domains**.

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST https://<your-railway-url>/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
```

Expected:
```
401
```

A `401` confirms:
- gunicorn is running
- The app started cleanly
- Auth middleware is enforcing

Any other status:
- `502` / `503` — gunicorn didn't start; check deploy logs for Python errors
- `000` / connection refused — the service isn't running; check Railway service status

---

## Done

Railway deployment is live. Next step: Vercel frontend deployment (separate spec).
