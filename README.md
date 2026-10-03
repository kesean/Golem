# Golem

A chatbot integration project, built as hands-on practice.

## Stack

| Layer | Tech |
|-------|------|
| API | Python · Flask · Anthropic SDK |
| Frontend | React · TypeScript · Tailwind · shadcn/ui |
| Auth | Clerk (signed-in users) · guest JWTs |
| Data | Convex (history, evals, stats) · Qdrant + Voyage AI (doc retrieval) |
| CI / Deploy | GitHub Actions · Railway · Vercel · Playwright · axe-core |

## What it does

Golem is a chatbot that answers technical questions in a structured format: summary, root cause, debug steps, and relevant docs. Each response is tagged with a product area so answers are easy to scan at a glance.

## Why I built it

I built Golem as practice wiring a full application together across services: auth, a backend API, a deployed frontend, CI, and end-to-end tests. The goal was to stay current with modern tooling by shipping something real end to end.

## Running locally

**Prerequisites:** Python 3, Node 18+, an [Anthropic API key](https://console.anthropic.com).

**1. Clone and install**

```bash
git clone https://github.com/kesean/golem.git
cd golem
```

```bash
# Python deps
pip install -r requirements.txt

# Frontend deps
cd frontend && npm install
```

**2. Configure environment**

Copy `.env.example` to `.env` in the project root and fill in your keys:

```
ANTHROPIC_API_KEY=...
CLERK_SECRET_KEY=...
CLERK_JWKS_URL=...
GUEST_JWT_SECRET=...   # generate with: openssl rand -hex 32
REDIS_URL=...          # optional — without it, rate limits are per-process (a warning is logged at startup)
QDRANT_URL=...         # optional — with QDRANT_API_KEY and VOYAGE_API_KEY enables doc retrieval;
QDRANT_API_KEY=...     #   without them, answers skip retrieval
VOYAGE_API_KEY=...
```

On startup the API checks the rate-limit storage and logs whether Redis is reachable. The limiter fails open (a Redis outage won't take `/ask` down), so an unreachable Redis is logged as an error instead of silently disabling limits.

Copy `.env.example` to `frontend/.env` and fill in the frontend keys:

```
VITE_CLERK_PUBLISHABLE_KEY=...
VITE_CONVEX_URL=...
```

**3. Start the servers**

```bash
# Terminal 1 — Flask API (port 5001)
python app.py

# Terminal 2 — Vite frontend (port 5173)
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

**4. Run the tests**

```bash
# Backend unit tests
pytest tests/

# Frontend unit tests (vitest)
cd frontend && npm test

# End-to-end + accessibility tests (Playwright + axe-core)
cd frontend && npm run test:e2e
```

**5. Running evals** (optional)

Run the V3a eval harness to measure answer quality against a fixed test set. Each case is scored by rule checks and an LLM grader, and compared to the baseline from the latest scheduled run.

```bash
# Run all eval cases and print a report to stdout
make eval

# Run offline (stubbed pipeline and grader, no uploads)
python -m evals.run --cases evals/fixtures/two_cases.json --no-upload --dry-judge EVAL_FAKE_PIPELINE=1

# Run without uploading to Convex
python -m evals.run --no-upload

# Exit codes
#   0: no regressions
#   1: harness error
#   2: regressions detected
```

**One-time setup for evals** (after cloning):

Set GitHub secrets for the weekly eval workflow (`.github/workflows/eval-weekly.yml`):
- `DEEPSEEK_API_KEY` — for the LLM grader (DeepSeek Flash)
- `CONVEX_SITE_URL` — your Convex deployment URL
- `EVAL_INGEST_SECRET` — for authenticating uploads to Convex; generate with `openssl rand -hex 32`
- Plus the existing secrets: `ANTHROPIC_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `VOYAGE_API_KEY`

Set Convex environment variables:

```bash
# Set the eval ingest secret (same value as the GitHub secret)
npx convex env set EVAL_INGEST_SECRET <generated-secret>

# Set the admin user list — comma-separated Clerk tokenIdentifiers
# Find your tokenIdentifier in the Convex dashboard (Logs → click a function call → look for "auth.tokenIdentifier")
# or check the Clerk dashboard or issue a test Convex function and inspect the identity
npx convex env set EVAL_ADMIN_IDS user_abc123,user_def456
```

**Notes:**

- Measured cost per run (weekly at off-peak): about **$0.44** per 30-case run ≈ **$1.90/month** (estimate; to be updated after first real run).
- GitHub disables scheduled workflows on public repos after 60 days of no repo activity. Check workflow status with `gh workflow view eval-weekly.yml` and re-enable if needed: `gh workflow enable eval-weekly.yml`.

## Deploying

The frontend deploys to Vercel. All deployment operations are managed from the repo root via `make`.

**One-time setup** (after cloning, requires [Vercel CLI](https://vercel.com/docs/cli)):

```bash
npm i -g vercel
vercel link    # when prompted, set Root Directory → frontend
```

**Deploy commands:**

| Command | What it does |
|---------|-------------|
| `make deploy-dev` | Deploy preview from `dev` branch |
| `make deploy-pre` | Deploy preview from `preview` branch |
| `make deploy-prod` | Deploy to production (from `main`) |
| `make status` | List recent deployments |
| `make logs URL=<url>` | Tail logs for a specific deployment |
| `make open` | Open the Vercel project dashboard |

Branch → environment mapping:

| Branch | Vercel environment |
|--------|--------------------|
| `dev` | Preview |
| `preview` | Preview |
| `main` | Production |

## Project phases

### Phase 1 — Basic app

| Feature | Status |
|---------|--------|
| Flask app scaffolding | ✅ Done |
| Anthropic SDK integration | ✅ Done |
| `/ask` POST endpoint | ✅ Done |
| Vanilla JS frontend with textarea + button | ✅ Done |
| Raw API response displayed in UI | ✅ Done |

### Phase 2 — Structured output

| Feature | Status |
|---------|--------|
| System prompt engineering for structured responses | ✅ Done |
| Four-section response: Summary, Root Cause, Debug Steps, Docs | ✅ Done |
| Docs rendered as clickable links when URLs detected | ✅ Done |
| Error handling for malformed responses | ✅ Done |

### Phase 3 — Streaming, history, product tags

| Feature | Status |
|---------|--------|
| `/ask` endpoint with response streaming | ✅ Done (removed in the V2 rewrite — see V2d for current status) |
| XML-tagged section format for incremental rendering | ✅ Done |
| Per-section streaming: text fades in chunk by chunk | ✅ Done |
| Response card fades in on first content arrival | ✅ Done |
| Conversation history (localStorage) | ✅ Done |
| Chat thread UI showing prior Q&A exchanges | ✅ Done |
| Product area tags (e.g. Authentication, Rate Limits, SDK) | ✅ Done |
| Product area tag badge displayed in UI | ✅ Done |

### Phase 4 — Data, auth, users

| Feature | Status |
|---------|--------|
| Vite frontend setup (migrate from raw JS) | ✅ Done |
| Clerk auth — sign-in/sign-up gate | ✅ Done |
| Flask JWT verification on /ask | ✅ Done |
| Convex schema + history table | ✅ Done |
| Replace localStorage with Convex per-user history | ✅ Done |

### Phase 5 — Security hardening

| Feature | Status |
|---------|--------|
| Remove unprotected `/ask` endpoint | ✅ Done |
| Derive Convex userId server-side via `ctx.auth` | ✅ Done |
| Replace indefinite JWKS cache with 1-hour TTL | ✅ Done |
| Question length limit (2000 chars) + Content-Type validation | ✅ Done |
| Distinct JWT error logging (expired, malformed, JWKS failure) | ✅ Done |
| Per-IP rate limiting on `/ask` (20 req/min) | ✅ Done |

### Phase 6 — Polish & UX

| Feature | Status |
|---------|--------|
| Markdown rendering in responses (code blocks, bold, lists) | ✅ Done |
| Mobile-responsive layout | ✅ Done |
| Keyboard shortcut hint (⌘↵ / Ctrl+↵) | ✅ Done |
| Loading skeleton while waiting for response | ✅ Done |

### Phase 7 — Product features

| Feature | Status |
|---------|--------|
| Multi-turn conversation with New Conversation button | ✅ Done |
| Search/filter history sidebar | ✅ Done |
| Copy response to clipboard | ✅ Done |
| Shareable links via `?share=` param | ✅ Done (lost in the React migration, restored — see Share links) |

### Phase 8 — Production deployment

| Feature | Status |
|---------|--------|
| Redis-backed rate limiting (replaces in-process limiter) | ✅ Done |
| Per-user daily limit: 5 requests/day (keyed to Clerk user ID) | ✅ Done |
| Global daily cap: 70 requests/day across all users | ✅ Done |
| CORS scoped to Vercel frontend origin | ✅ Done |
| CORS allowed for Vercel preview deployments via `PREVIEW_ORIGIN_REGEX` | ✅ Done |
| Flask backend deployed to Railway (with Redis add-on) | ✅ Done |
| Frontend deployed to Vercel — Dev / Pre / Prod environments | ✅ Done |
| Makefile targets for terminal-driven deployments (`deploy-dev`, `deploy-pre`, `deploy-prod`, `status`, `logs`, `open`) | ✅ Done |
| Production environment variables configured (no secrets in code) | ✅ Done |
| GitHub Actions: unit tests, e2e (Playwright), doc-source validation | ✅ Done |
| E2E tests gate PRs — run against Vercel Preview on every deployment | ✅ Done |

---

## V2 — AI system upgrades

### V2a — Observability

| Feature | Status |
|---------|--------|
| Log token usage + latency on every `/ask` request | ✅ Done |
| Convex eval table (query, response, latency, user feedback) | ✅ Done |

### V2b — Retrieval-Augmented Generation (RAG)

| Feature | Status |
|---------|--------|
| Embed documentation chunks into vector store | ✅ Done |
| Top-k retrieval via `retrieve_docs` tool | ✅ Done |

### V2c — Tool use

| Feature | Status |
|---------|--------|
| `retrieve_docs()` tool backed by vector search | ✅ Done |
| `api_lookup()` tool for live API data | ✅ Done |
| `chat.py` tool loop — LLM decides which tools to call | ✅ Done (removed below) |
| Pre-retrieve docs before Claude call — eliminates tool-use round trip | ✅ Done |
| Cap tool loop to 2 Claude API calls max | ✅ Done |
| Remove `api_lookup` tool — guarantees single Claude API call | ✅ Done |
| Skip `retrieve_docs` when RAG backends are not configured | ✅ Done |
| Delete dead tool-loop code and `api_lookup.py`; `chat.py` is a single Claude call | ✅ Done |
| Upgrade model to `claude-sonnet-5` | ✅ Done |

### V2d — Frontend upgrade

| Feature | Status |
|---------|--------|
| Migrate to React + TypeScript | ✅ Done |
| Tailwind CSS + shadcn/ui component library | ✅ Done |
| Component architecture (Header, QuestionInput, ResponsePanel, SectionCard, ProductBadge, ResponseActions, FeedbackButtons, HistoryPalette) | ✅ Done |
| Hooks: `useChat`, `useHistory`, `useTheme` | ✅ Done |
| History palette with Ctrl+K (CommandDialog) | ✅ Done |
| Dark mode toggle with localStorage persistence | ✅ Done |
| DOMPurify-sanitized markdown rendering in React | ✅ Done |
| Animated thinking indicator during response loading | ✅ Done |
| Restore streaming responses — `/ask` streams SSE, sections fade in as text arrives | ✅ Done |
| Debug panel showing retrieved doc chunks | ✅ Done |

### Guest access

| Feature | Status |
|---------|--------|
| Guest JWT access — try chatbot without sign-in | ✅ Done |
| Animated loading screen during guest token fetch | ✅ Done |
| History palette shows sign-in prompt for guest users | ✅ Done |
| Per-user daily cap reduced to 5 requests | ✅ Done |
| Prompt injection defense — `<user_input>` XML delimiters + system prompt reinforcement | ✅ Done |
| Cold-start warm-up disclaimer after 2 s of loading | ✅ Done |

### Demo experience

| Feature | Status |
|---------|--------|
| Global "questions answered" counter in the header (Convex `stats` table, includes guests) | ✅ Done |
| Suggested demo questions on the empty state | ✅ Done |
| First-visit guided tour with a header replay button | ✅ Done |
| Empty-state hero and clearer input placeholder | ✅ Done |

### Doc citations

| Feature | Status |
|---------|--------|
| Canonical public doc URLs on retrieved chunks (Clerk, MDN) | ✅ Done |
| System prompt cites only retrieved docs | ✅ Done |
| Doc links parsed robustly (markdown/paren/angle URLs, title split from URL, userinfo URLs rejected) | ✅ Done |
| Log cited `<docs>` URLs that weren't retrieved (`docs-url-miss` warning) | ✅ Done |

### Notebook-style answer

| Feature | Status |
|---------|--------|
| Answer rendered as a notebook page with checkable debug steps and real doc links | ✅ Done |
| Answer reveal — marker sweeps under Cause, steps land in turn (reduced-motion safe) | ✅ Done |

### Reliability

| Feature | Status |
|---------|--------|
| Startup rate-limit storage check — logs when Redis is missing or unreachable | ✅ Done |
| Limiter storage errors visible in logs (root log handler under gunicorn) | ✅ Done |
| Console warning when the global stats increment fails | ✅ Done |

### Accessibility

| Feature | Status |
|---------|--------|
| Accessibility audit fixes — stronger focus ring, skip-to-question link, heading structure, 44px touch targets | ✅ Done |
| Live region announces "analyzing" and "answer ready" | ✅ Done |
| axe-core scans in the e2e suite (empty/answered states, phone + desktop, light + dark, tour, history palette) | ✅ Done |
| History palette: proper dialog name/description, labelled search input, announced empty and no-match states | ✅ Done |

### Security review follow-ups

| Feature | Status |
|---------|--------|
| Full-repo security review — no high-confidence vulnerabilities found | ✅ Done |
| Public `history.getById` takes a typed history ID and no longer returns the owner's user ID | ✅ Done |
| `stats.increment` stays public for guests; accepted risk documented in code | ✅ Done |
| Answer markdown sanitized against an allowlist — no forms, images, styles, classes, `aria-*`/`data-*` attributes; links limited to http(s)/mailto and open in a new tab | ✅ Done |

### Share links

| Feature | Status |
|---------|--------|
| `?share=<id>` opens the shared question and answer in the normal app (guests and signed-in users) | ✅ Done |
| Share param stripped from the URL; lookup times out after 8 s so a broken link never loads forever | ✅ Done |
| Plain-text provenance notice ("Shared by another user…") stays visible while a shared answer is shown, announced to screen readers | ✅ Done |
| Shared answers hide the product tag and feedback buttons, and never write history, evals, or stats on load | ✅ Done |
| A late share lookup never overwrites a question the visitor has started; the first-visit tour doesn't cover a shared answer | ✅ Done |
| Unit tests for the hook, notice, panel, and app flow; e2e for broken links (axe clean, light + dark) | ✅ Done |

Known limitation: a guest who signs in from a shared answer loses it, because the app remounts on sign-in.

---

## V3 — Next steps

Planned phases, built one at a time in this order. Each phase starts with a spec (`spec.md`) and a task list (`tasks.md`).

| Phase | Goal | Status |
|-------|------|--------|
| V3a — Eval harness | A versioned set of test questions graded automatically (rule checks plus a low-cost LLM grader for groundedness and coverage), run weekly with run-to-run comparison and an auto-opened GitHub issue on regression, so every later change is measurable | ✅ Done |
| V3b — Deeper AI features | Diagnose pasted stack traces and HTTP logs, inline citations linked to the exact retrieved passage, follow-up suggestions, live tool calls | ⏳ Planned |
| V3c — Agent harness / MCP | Expose Golem as an MCP server or Agent SDK tool so coding agents can get grounded debugging answers, with machine-client auth and per-client usage limits | ⏳ Planned |
| V3d — Distinctive UI redesign | A visual identity that doesn't look generated: type, colour, and layout for the answer page, plus a landing/demo page | ⏳ Planned |

### V3a — Eval harness

| Feature | Status |
|---------|--------|
| Test set: 30 hand-written cases covering Clerk auth, web platform (CORS/fetch/streaming), rate limits, injection defense | ✅ Done |
| Run all cases through the production pipeline (`chat.stream_run` in-process, no `/ask` rate limit) | ✅ Done |
| Rule checks: completed, format, product tag, citations, retrieval | ✅ Done |
| LLM grader (DeepSeek Flash): groundedness and coverage (1–5), with retry on invalid JSON | ✅ Done |
| Regression detection: mean score drop (>0.3), rule flips, case score drop (≥2), error rate (>20%), slow 8-week decline | ✅ Done |
| Convex storage: `evalRuns` and `evalResults` tables with authenticated HTTP POST and GET endpoints | ✅ Done |
| Local run: `make eval` with `--no-upload`, `--dry-judge`, `EVAL_FAKE_PIPELINE=1` for offline testing | ✅ Done |
| Scheduled run: weekly cron (Sunday 06:00 UTC) with `workflow_dispatch` trigger; stored and artifacted | ✅ Done |
| GitHub alerting: auto-open or comment on `eval-regression` issue with summary and regression details | ✅ Done |
| Admin dashboard (`/evals`): trend chart (26 weeks), run list, case details with grader reason and score deltas | ✅ Done |
