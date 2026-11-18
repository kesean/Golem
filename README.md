# Golem

A chatbot integration project, built as hands-on practice.

## Stack

| Layer | Tech |
|-------|------|
| API | Python · Flask · Anthropic SDK |
| Frontend | React · TypeScript · Tailwind · shadcn/ui |
| Auth | Clerk (signed-in users) · guest JWTs |
| Data | Convex (history, evals, stats) · Qdrant + Voyage AI (doc retrieval) |
| Security | CSP and security headers (`frontend/vercel.json`) · Vercel WAF rate limit · Flask-Limiter on Redis |
| CI / Deploy | GitHub Actions · Vercel · Playwright · axe-core |

## What it does

Golem is a chatbot that answers technical questions in a structured format: summary, root cause, debug steps, and relevant docs. Each response is tagged with a product area so answers are easy to scan at a glance.

## Why I built it

I built Golem as practice wiring a full application together across services: auth, a backend API, a deployed frontend, CI, and end-to-end tests. The goal was to stay current with modern tooling by shipping something real end to end.

## Running locally

**Prerequisites:** Python 3.12 (pinned in `.python-version`), Node 24 (what CI uses), an [Anthropic API key](https://console.anthropic.com).

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

#### Rate limits

All limits are fixed windows enforced in `app.py`. Redis (`REDIS_URL`) makes them shared across instances.

| Limit | Route | Value | Keyed on |
|---|---|---|---|
| Per IP, per minute | `/ask` | 20 per minute | client IP (before auth) |
| Per IP, per day, guests | `/ask` | 10 per day | client IP |
| Per IP, per day, signed-in | `/ask` | 200 per day (backstop) | client IP |
| Per user, per day | `/ask` | 5 per day | Clerk `sub`; guests share one bucket per IP |
| Global, per day, prod origins | `/ask` | 70 per day | everyone whose `Origin` is not a preview origin |
| Global, per day, preview origins | `/ask` | 20 per day (`PREVIEW_GLOBAL_DAILY_LIMIT`) | `Origin` matching `PREVIEW_ORIGIN_REGEX`, not `FRONTEND_ORIGIN` |
| Guest mints, per hour | `/guest-token` | 10 per hour | client IP |
| Guest mints, per day | `/guest-token` | 20 per day | client IP |

- The per-minute limit runs before auth, so unauthenticated requests count against it.
- Every other `/ask` limit is charged after the token is verified and the request is valid. Garbage tokens, forged tokens and 400 responses use no daily quota.
- Charge order is per-IP daily, then per-user, then global. A request refused early never uses a later budget. A request refused by the global cap is still charged to its user.
- Preview frontends (Vercel previews and the e2e job) charge their own 20/day global bucket, so they cannot use up the prod 70/day budget. A missing, empty or invalid `Origin`, and an `Origin` equal to `FRONTEND_ORIGIN`, count as prod. The prod frontend origin must equal `FRONTEND_ORIGIN` exactly. If `FRONTEND_ORIGIN` is unset while `PREVIEW_ORIGIN_REGEX` is set, prod visitors can match the regex and be charged to the preview bucket, and startup logs a WARNING. `PREVIEW_GLOBAL_DAILY_LIMIT` overrides the 20; a value that is not a positive integer logs an error and uses 20.
- Tradeoff: `Origin` is set by the client, so a non-browser caller can send a preview `Origin` to charge the preview bucket instead. That only moves its spend into the 20/day cap. Worst-case total global spend is 70 (prod) + 20 (preview) = 90 per day, not 70.
- A guest's bucket is keyed on IP, not on the guest token, because tokens are free to mint.
- Users behind one NAT address share the per-IP limits (20 per minute, and 10 per day for guests).
- The limiter fails open. If storage errors at runtime, the first error logs one `Rate limiting is NOT enforced` WARNING per process. Each later error logs at ERROR only.

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
cd frontend && npx playwright install chromium   # once
cd frontend && npm run test:e2e
```

Locally, Playwright starts the dev server itself with `VITE_TEST_BYPASS_AUTH=true` (a signed-in test seam that only exists in non-production builds) and mocks `/ask`, so no keys are needed. Set `BASE_URL` to run the same specs against a deployed preview; specs that need the local seam skip themselves in that case. For a protected preview, set `VERCEL_BYPASS_TOKEN`: the specs send it only to the `BASE_URL` origin (`e2e/fixtures.ts`), never to Clerk, Convex or the API.

The e2e suite covers the answer flow, feedback, share links, the history palette, the first-visit tour, the evals dashboard, a 360px phone layout, dark mode, reduced motion, the error and retry state, and a CSP spec that fails on any `securitypolicyviolation`. The backend uses Python 3.12 in CI; if your local virtualenv is older or newer, recreate it with `uv venv --python 3.12`.

**5. Running evals** (optional)

Run the V3a eval harness to measure answer quality against a fixed test set. Each case is scored by rule checks and an LLM grader, and compared to the baseline from the latest scheduled run.

```bash
# First, set env vars (evals/ does not auto-load .env):
set -a; source .env; set +a

# Run all eval cases, upload results, and print a report to stdout
# Requires: DEEPSEEK_API_KEY, CONVEX_SITE_URL, EVAL_INGEST_SECRET
make eval

# Run offline (stubbed pipeline and grader, no uploads)
EVAL_FAKE_PIPELINE=1 python -m evals.run --cases evals/fixtures/two_cases.json --no-upload --dry-judge

# Run without uploading to Convex
# If CONVEX_SITE_URL or EVAL_INGEST_SECRET are not set, skips baseline fetch and continues
python -m evals.run --no-upload

# Exit codes
#   0: clean run, no regressions
#   1: harness error (no case could be graded, upload failure, crash)
#   2: regressions detected (CI job succeeds but opens a regression issue)
#
# Weekly workflow: exit codes other than 0 or 2 fail the job and open a harness-error issue
```

**One-time setup for evals** (after cloning):

Set GitHub secrets for the weekly eval workflow (`.github/workflows/eval-weekly.yml`):
- `DEEPSEEK_API_KEY` — for the LLM grader (DeepSeek Flash)
- `CONVEX_SITE_URL` — HTTP Actions URL shown in the Convex dashboard deployment settings (format: `https://<deployment>.convex.site`)
- `EVAL_INGEST_SECRET` — for authenticating uploads to Convex; generate with `openssl rand -hex 32`
- Plus the existing secrets: `ANTHROPIC_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `VOYAGE_API_KEY`

Set GitHub repository variables (Settings → Variables):
- `EVALS_DASHBOARD_URL` (optional) — link added to regression issues; e.g., `https://your-golem-app.vercel.app/evals`

Set Convex environment variables (use `--prod` for the deployment the weekly CI run uploads to):

```bash
# Set the eval ingest secret (same value as the GitHub secret)
npx convex env set --prod EVAL_INGEST_SECRET <generated-secret>

# Set the admin user list — comma-separated Clerk tokenIdentifiers in the format: <issuer URL>|<user id>
# Example: https://your-app.clerk.accounts.dev|user_2abc...
# To find your tokenIdentifier: temporarily add console.log((await ctx.auth.getUserIdentity())?.tokenIdentifier)
# to a Convex query, sign in, and check the Convex dashboard Logs tab
npx convex env set --prod EVAL_ADMIN_IDS "https://your-app.clerk.accounts.dev|user_abc123,https://your-app.clerk.accounts.dev|user_def456"
```

**Notes:**

- Estimated cost per run (weekly at off-peak): about **$0.44** per 30-case run ≈ **$1.90/month** (to be updated after first real run).
- GitHub disables scheduled workflows on public repos after 60 days of no repo activity. Check workflow status with `gh workflow view eval-weekly.yml` and re-enable if needed: `gh workflow enable eval-weekly.yml`.

## Security

What is enforced today, and where to change it.

**Request validation (`app.py`).** `/ask` needs a JSON object body. `question` is a string of at most 2000 characters. `history` is a list of at most 20 turns, each `{role: user|assistant, content: string}` with non-empty content of at most 2000 characters (user) or 12000 (assistant, because turns carry the raw XML answer). Bodies over 512 KB get a JSON 413. Errors sent to the client are generic; the detail is logged server-side. The Flask debugger runs only with `FLASK_DEBUG=1`.

**Auth.** Clerk JWTs and guest JWTs are verified on every `/ask`. The Clerk JWKS is cached for an hour, refetched at most once a minute when a token carries an unknown key id, and the stale copy is served if Clerk is unreachable. An upstream failure returns 503, not 401.

**Prompt injection.** `<` and `>` are escaped in the question and in user history turns, and the retrieved-docs sentinels are stripped (Unicode dashes, zero-width characters and case variants included). The `<docs>` block in the final answer is filtered to URLs that were actually retrieved. It fails closed, so an unclosed block is dropped. Streamed text is not filtered while it arrives; the answer the UI keeps once the stream ends is the filtered one.

**Response headers.** The API sends `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The frontend sends a CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy` and `Permissions-Policy`, all set in `frontend/vercel.json` (Vercel adds HSTS itself). `script-src` has no `unsafe-inline` or `unsafe-eval`; the one inline script (the pre-paint theme script in `index.html`) is allowed by hash, and `tests/security-headers.test.ts` fails if the script changes without the hash being updated. Clerk telemetry is turned off in `main.tsx` because the CSP does not allow `clerk-telemetry.com`. When you add a third-party origin, add it to `connect-src` (or the relevant directive) and run the CSP spec.

**Edge.** One Vercel WAF rule on `golem-api` covers `/ask` and `/guest-token`: 30 requests per 60 seconds per IP. It is in `log` mode; check the firewall traffic page, then switch it to `deny`. The plan allows one rate-limit rule, so both routes share it. Manage it with `vercel firewall rules list` and `vercel firewall publish`.

**Shared answers.** `?share=` answers are user-written, so doc links are limited to `https` URLs on `clerk.com` subdomains and `developer.mozilla.org`. Other links render as plain text, `mailto:` links are dropped, and the notice says the answer is not verified by Golem. A deleted or evicted share shows "may have been deleted by its owner or removed to make room".

**Convex.** Reads and writes are bounded: a user's history list returns at most 100 rows and stores at most 200 (the oldest is evicted), question and answer sizes are capped, a user can create at most 200 eval entries per 24 hours, and eval ingest is idempotent on `gitSha` plus `startedAt`. Convex validator errors on ingest return a generic "Invalid payload".

**CI and config.** Every workflow runs with a read-only `GITHUB_TOKEN` (the weekly eval job also gets `issues: write`). The e2e job runs only for deployments of a commit that is the head of a branch in this repo, and `VERCEL_BYPASS_TOKEN` is passed to that job alone. Doc sources for retrieval are pinned to commit SHAs in `scripts/embed_docs.py` (override with `CLERK_DOCS_REF` and `MDN_CONTENT_REF`; the `validate-doc-sources` workflow checks the pins). `PREVIEW_ORIGIN_REGEX` is compiled as a full match (`\A(?:…)\Z`), and an unanchored value logs a warning. `.claude/settings.local.json` is not tracked.

**Known gaps.** There is no CAPTCHA or bot check on `/guest-token` or `/ask` (Turnstile or BotID would need keys). The CSP uses wildcards for the Convex and Clerk hosts because preview deployments use other hosts. Streamed deltas reach the client before filtering. The Clerk sign-in modal is not covered by CI e2e because Vercel previews build with `VITE_TEST_BYPASS_AUTH=true`. `npm audit` still reports findings that need breaking upgrades (vitest, vite).

## Deploying

Everything runs on Vercel as two projects, both connected to this GitHub repo:

| Project | Root directory | What it serves | URL |
|---------|----------------|----------------|-----|
| `golem` | `frontend` | React app (Vite build, Convex deploy) | https://golem-support.vercel.app |
| `golem-api` | `.` | Flask API as one Python function (`app.py`), rate limits in Upstash Redis | https://golem-api.vercel.app |

Pushing to `main` deploys both projects to production. Pull requests get a `golem` preview, and the e2e tests run against it. `golem-api` skips preview builds (its ignored build step is `[ "$VERCEL_GIT_COMMIT_REF" != "main" ]`), so frontend previews call the production API, which allows them through `PREVIEW_ORIGIN_REGEX`.

Environment variables live in Vercel (`vercel env ls`). `golem` holds `VITE_API_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_CONVEX_URL` and `CONVEX_DEPLOY_KEY`. `golem-api` holds the API keys from step 2 of *Running locally*, plus `FRONTEND_ORIGIN` and `PREVIEW_ORIGIN_REGEX`, and optionally `PREVIEW_GLOBAL_DAILY_LIMIT` (default 20, see *Rate limits*). Local development leaves `VITE_API_URL` unset, so Vite proxies `/ask` to the Flask server on port 5001.

**One-time setup** (after cloning, requires [Vercel CLI](https://vercel.com/docs/cli)):

```bash
npm i -g vercel
vercel link                   # repo root → golem-api
cd frontend && vercel link    # frontend → golem
```

**Manual deploy commands** (run from the repo root, so they act on `golem-api`):

| Command | What it does |
|---------|-------------|
| `make deploy-dev` / `make deploy-pre` | Deploy a preview |
| `make deploy-prod` | Deploy to production |
| `make status` | List recent deployments |
| `make logs URL=<url>` | Tail logs for a specific deployment |
| `make open` | Open the Vercel project dashboard |

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
| Flask backend deployed to Railway (with Redis add-on) | ✅ Done (moved to Vercel, see below) |
| Flask backend moved from Railway to Vercel (`golem-api` project, Upstash Redis); Railway retired | ✅ Done |
| Frontend deployed to Vercel — Dev / Pre / Prod environments | ✅ Done |
| Makefile targets for terminal-driven deployments (`deploy-dev`, `deploy-pre`, `deploy-prod`, `status`, `logs`, `open`) | ✅ Done |
| Production environment variables configured (no secrets in code) | ✅ Done |
| GitHub Actions: unit tests, e2e (Playwright), doc-source validation | ✅ Done |
| E2E tests gate PRs — run against Vercel Preview on every deployment | ✅ Done |

### Phase 9 — Audit hardening (November 2026)

Findings came from a debug audit, a design review and a security review. Details of each control are in *Security* and *Rate limits* above.

| Feature | Status |
|---------|--------|
| `/ask` body and history validation, 512 KB body cap, generic client errors | ✅ Done |
| JWKS refetch on unknown key, stale-cache fallback, 503 on upstream failure | ✅ Done |
| Per-IP limits before auth, atomic quota charging, guest limits keyed on IP | ✅ Done |
| Separate global bucket for preview origins; `PREVIEW_ORIGIN_REGEX` normalised to a full match | ✅ Done |
| Doc-citation filter fails closed; prompt sentinels and angle brackets neutralised | ✅ Done |
| Eval judge input escaping; error-rate regression checked without a baseline; pinned doc sources | ✅ Done |
| Convex reads and writes bounded; ingest idempotent; stats increment race closed | ✅ Done |
| Shared answers: doc-host allowlist, markdown links sanitised, "not verified" notice | ✅ Done |
| CSP and security headers, hash-pinned theme script, CSP e2e spec; Clerk telemetry off | ✅ Done |
| Vercel WAF rate-limit rule on `/ask` and `/guest-token` (log mode) | ✅ Done |
| Workflows on read-only tokens; e2e guard; bypass token scoped to the preview origin | ✅ Done |
| `useChat` fixes: stale asks cannot overwrite newer ones, history keeps whole Q/A pairs, retry on error | ✅ Done |
| UI: dialog rebuilt on shared dialog, control and dark-mode contrast, reduced motion, pre-paint theme, 44px targets, phone header wrap | ✅ Done |
| Unused Preview secrets removed from `golem-api` | ✅ Done |
| WAF rule switched from `log` to `deny` | ⏳ After reviewing traffic |
| CAPTCHA or bot check on `/guest-token` and `/ask` (Turnstile, BotID) | ⏳ Needs keys |

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
| Limiter storage errors visible in logs (root log handler, so they reach the Vercel function logs) | ✅ Done |
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
