# Dev Support AI

A developer support chatbot that answers technical questions the way a developer support engineer would — structured, specific, and actionable. Built as a portfolio project to practice Claude API integration, prompt engineering, and modern web tooling.

![Dev Support AI — V2 Architecture](docs/assets/images/architecture.png)

## What it does

You type a technical question. The app streams back a response broken into four sections:

- **Summary** — a concise answer
- **Root Cause** — why the problem happens
- **Debug Steps** — numbered steps to resolve it
- **Docs** — relevant documentation links

Each response is also tagged with a product area (e.g. Authentication, Rate Limits, SDK) so answers are easy to scan at a glance. History is saved per-user in the cloud and visible in a sidebar.

Visitors can try the chatbot without creating an account — a signed guest JWT is issued automatically on first load, giving up to 5 questions before prompting to sign in.

## Stack

| Layer | Tech |
|-------|------|
| API | Python · Flask · Anthropic SDK |
| Auth | Clerk (sign-in gate + JWT verification) |
| Database | Convex (per-user history) |
| Frontend | Vite · React · TypeScript · Tailwind · shadcn/ui |

## Running locally

**Prerequisites:** Python 3, Node 18+, accounts on [Anthropic](https://console.anthropic.com), [Clerk](https://dashboard.clerk.com), and [Convex](https://dashboard.convex.dev).

**1. Clone and install**

```bash
git clone https://github.com/kesean/dev-support-chatbot.git
cd dev-support-chatbot
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
```

Copy `.env.example` to `frontend/.env` and fill in the frontend keys:

```
VITE_CLERK_PUBLISHABLE_KEY=...
VITE_CONVEX_URL=...
```

To get your Convex URL, run `npx convex dev` from the `frontend/` directory once to initialize the project.

**3. Start the servers**

```bash
# Terminal 1 — Flask API (port 5001)
python app.py

# Terminal 2 — Vite frontend (port 5173)
cd frontend && npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Deploying

The frontend deploys to Vercel. All deployment operations are managed from the repo root via `make`.

**One-time setup** (after cloning, requires [Vercel CLI](https://vercel.com/docs/cli)):

```bash
npm i -g vercel
vercel link    # when prompted, set Root Directory → frontend
```

This creates `.vercel/project.json` at the repo root (gitignored). All `make` targets depend on it.

**Deploy commands:**

| Command | What it does |
|---------|-------------|
| `make deploy-dev` | Deploy preview from `dev` branch |
| `make deploy-pre` | Deploy preview from `preview` branch |
| `make deploy-prod` | Deploy to production (from `main`) |
| `make status` | List recent deployments across all environments |
| `make logs URL=<deployment-url>` | Tail logs for a specific deployment |
| `make open` | Open the project dashboard on vercel.com |

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
| `/ask` endpoint with response streaming | ✅ Done |
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
| Shareable links via `?share=` param | ✅ Done |

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
| Embed Clerk documentation chunks into Qdrant vector store | ✅ Done |
| Voyage AI embeddings + Qdrant Cloud vector search | ✅ Done |
| Top-k retrieval via `retrieve_docs` tool | ✅ Done |

### V2c — Tool use

| Feature | Status |
|---------|--------|
| `retrieve_docs()` tool backed by Qdrant vector search | ✅ Done |
| `api_lookup()` tool for live Clerk + Anthropic API data | ✅ Done |
| `chat.py` tool loop — LLM decides which tools to call | ✅ Done |
| Pre-retrieve docs before Claude call — eliminates tool-use round trip | ✅ Done |
| Cap tool loop to 2 Claude API calls max | ✅ Done |
| Remove `api_lookup` tool — guarantees single Claude API call | ✅ Done |
| Skip `retrieve_docs` when RAG backends are not configured | ✅ Done |

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
| Restore streaming responses | 🔲 Planned |
| Debug panel showing retrieved doc chunks | 🔲 Planned |

### Portfolio hardening

| Feature | Status |
|---------|--------|
| Guest JWT access — try chatbot without Clerk sign-in | ✅ Done |
| Animated loading screen during guest token fetch | ✅ Done |
| History palette shows sign-in prompt for guest users | ✅ Done |
| Per-user daily cap reduced to 5 requests | ✅ Done |
| Prompt injection defense — `<user_input>` XML delimiters + system prompt reinforcement | ✅ Done |
| Cold-start warm-up disclaimer after 2 s of loading | ✅ Done |
