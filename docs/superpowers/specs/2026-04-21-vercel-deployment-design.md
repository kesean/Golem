# Vercel Deployment Design

**Date:** 2026-04-21
**Scope:** Frontend deployment to Vercel with Dev / Pre / Prod environments managed from the terminal via Makefile

---

## Overview

Deploy the Vite frontend (`frontend/`) to Vercel as a single project with three environments. All deployment operations are driven from the terminal via Makefile targets wrapping the Vercel CLI. Railway (Flask backend) stays as a single production deployment — out of scope for this spec.

---

## Environment Mapping

| Git branch | Vercel environment | URL pattern |
|---|---|---|
| `dev` | Preview (named "dev") | `dev-<project>.vercel.app` |
| `preview` | Preview (named "preview") | `preview-<project>.vercel.app` |
| `main` | Production | `<project>.vercel.app` |

Vercel supports one Production environment and unlimited named Preview environments. Dev and Pre both use Preview environments pinned to their respective branches. Production is reserved for `main`.

---

## Files Added

### `vercel.json` (repo root)

Sets the build root to `frontend/` and declares the framework:

```json
{
  "buildCommand": "cd frontend && npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "cd frontend && npm install",
  "framework": null
}
```

Branch → environment mapping is handled by Vercel's Git integration configured at project link time, not in `vercel.json`.

### `Makefile` (repo root)

```makefile
VERCEL = vercel --cwd frontend --yes

.PHONY: deploy-dev deploy-pre deploy-prod status logs open

deploy-dev:
	$(VERCEL) pull --environment=preview
	$(VERCEL) deploy

deploy-pre:
	$(VERCEL) pull --environment=preview
	$(VERCEL) deploy

deploy-prod:
	$(VERCEL) pull --environment=production
	$(VERCEL) deploy --prod

status:
	$(VERCEL) ls

logs:
	$(VERCEL) logs $(URL)

open:
	$(VERCEL) open
```

Usage:
```bash
make deploy-dev
make deploy-pre
make deploy-prod
make status
make logs URL=https://dev-<project>.vercel.app
make open
```

`vercel pull` runs before each deploy to sync the correct environment variables locally before the build.

`deploy-dev` and `deploy-pre` issue identical CLI commands. Vercel resolves which named Preview environment to target from the current git branch — running `make deploy-dev` from the `dev` branch targets the "dev" environment automatically.

---

## One-Time Setup (already completed)

1. **Install Vercel CLI** — `npm i -g vercel` ✓
2. **Set token** — `VERCEL_TOKEN` added to `.bashrc` ✓
3. **Link project** — run `vercel link` inside `frontend/` to create `.vercel/project.json`
   - This file contains `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` — needed by the CLI
   - `.vercel/` is gitignored; each developer runs `vercel link` once locally

---

## Environment Variables

Frontend env vars (`VITE_CLERK_PUBLISHABLE_KEY`, `VITE_CONVEX_URL`) must be set per environment in the Vercel dashboard or via `vercel env add`. Each environment (Development, Preview, Production) gets its own values.

`vercel pull` syncs these to a local `.env.vercel` file before each build.

---

## What Is Not In Scope

- Railway multi-environment setup (separate future spec)
- Custom domain configuration
- CI/CD (GitHub Actions) — terminal-only workflow for now
- `vercel promote` workflow — promoting a Preview to Production by URL rather than branch push
