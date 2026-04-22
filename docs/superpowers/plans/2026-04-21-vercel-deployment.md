# Vercel Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Vercel to deploy the Vite frontend with three environments (Dev/Pre/Prod) and expose all deployment operations via Makefile targets.

**Architecture:** A `vercel.json` at the repo root points Vercel at the `frontend/` build. A `Makefile` wraps the Vercel CLI with named targets for deploy, status, logs, and open. Branch → environment mapping (`dev` → Dev, `preview` → Pre, `main` → Prod) is handled by Vercel's Git integration at link time.

**Tech Stack:** Vercel CLI, GNU Make, Vite (existing)

---

### Task 1: Set up feature branch and update `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Check out the feature branch**

```bash
git fetch origin
git checkout feature/vercel-deployment
```

Expected: on branch `feature/vercel-deployment`

- [ ] **Step 2: Add `.vercel/` to `.gitignore`**

Open `.gitignore` and append:

```
# Vercel
.vercel/
```

- [ ] **Step 3: Verify the entry is there**

```bash
grep -n ".vercel" .gitignore
```

Expected output contains `.vercel/`

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .vercel/ directory"
```

---

### Task 2: Link the project to Vercel

**Files:**
- Creates: `.vercel/project.json` at repo root (gitignored)

- [ ] **Step 1: Run `vercel link` from the repo root**

```bash
vercel link
```

Follow the prompts:
- Link to existing project or create new → **Create new project** (or link existing)
- Project name → accept default or set to `dev-support-chatbot`
- Which scope → your personal account or team
- Root Directory → enter `frontend`

Expected: `.vercel/project.json` created at the repo root

> **Important:** Run from the repo root, not from inside `frontend/`. The Makefile runs `vercel` commands from the repo root, so `project.json` must be there. If you run `vercel link` from `frontend/`, commands will fail.

- [ ] **Step 2: Confirm `project.json` exists at repo root and contains org + project IDs**

```bash
cat .vercel/project.json
```

Expected output (values will differ):
```json
{
  "orgId": "team_xxxx",
  "projectId": "prj_xxxx"
}
```

- [ ] **Step 3: Verify `.vercel/` is gitignored**

```bash
git status .vercel
```

Expected: nothing listed (directory is ignored)

---

### Task 3: Create `vercel.json`

**Files:**
- Create: `vercel.json`

- [ ] **Step 1: Create `vercel.json` at the repo root**

```json
{
  "buildCommand": "cd frontend && npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "cd frontend && npm install",
  "framework": null
}
```

- [ ] **Step 2: Verify it parses as valid JSON**

```bash
python3 -c "import json; json.load(open('vercel.json')); print('valid')"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add vercel.json
git commit -m "chore: add vercel.json with frontend build config"
```

---

### Task 4: Create `Makefile`

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create `Makefile` at the repo root**

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

> Note: Makefile indentation MUST use tabs, not spaces. If your editor converts tabs to spaces, the `make` command will error with "missing separator".

- [ ] **Step 2: Verify `make` can parse the file**

```bash
make --dry-run status
```

Expected: prints the `vercel ls` command without executing it (no "missing separator" error)

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile with Vercel deploy targets"
```

---

### Task 5: Smoke test `make status`

**Files:** none

- [ ] **Step 1: Run `make status`**

```bash
make status
```

Expected: Vercel CLI lists recent deployments for the linked project. Output includes deployment URLs, states (READY / BUILDING / ERROR), and timestamps.

If you see `Error: No project found` — re-run `vercel link` inside `frontend/` (Task 2, Step 1).

---

### Task 6: Create `dev` and `preview` branches

**Files:** none

These branches need to exist for Vercel's Git integration to map them to Preview environments.

- [ ] **Step 1: Create and push `dev` branch**

```bash
git checkout -b dev
git push -u origin dev
git checkout feature/vercel-deployment
```

- [ ] **Step 2: Create and push `preview` branch**

```bash
git checkout -b preview
git push -u origin preview
git checkout feature/vercel-deployment
```

- [ ] **Step 3: Verify both branches exist on remote**

```bash
git branch -r | grep -E "dev|preview"
```

Expected:
```
origin/dev
origin/preview
```

---

### Task 7: Test `make deploy-dev`

**Files:** none

- [ ] **Step 1: Switch to the `dev` branch**

```bash
git checkout dev
git merge feature/vercel-deployment
```

- [ ] **Step 2: Run `make deploy-dev`**

```bash
make deploy-dev
```

Expected: Vercel CLI pulls env vars, builds the frontend, and prints a Preview deployment URL like `https://dev-support-chatbot-<hash>-<org>.vercel.app`.

- [ ] **Step 3: Open the deployment URL in a browser and verify the app loads**

Copy the URL from the output and open it. Confirm the chat UI renders and the sign-in page appears (Clerk auth wall).

- [ ] **Step 4: Run `make open` to verify that target works**

```bash
make open
```

Expected: opens the project overview page on vercel.com in a browser.

- [ ] **Step 5: Switch back to feature branch**

```bash
git checkout feature/vercel-deployment
```

---

### Task 8: Open pull request

**Files:** none

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin feature/vercel-deployment
```

- [ ] **Step 2: Open a PR from `feature/vercel-deployment` → `main`**

```bash
gh pr create \
  --title "chore: add Vercel deployment config and Makefile" \
  --body "Adds vercel.json and Makefile targets for deploying the frontend to Dev/Pre/Prod environments via the Vercel CLI. See docs/superpowers/specs/2026-04-21-vercel-deployment-design.md."
```

- [ ] **Step 3: Confirm PR is open**

```bash
gh pr view --web
```
