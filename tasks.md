# Tasks — V3a Eval harness

Source of truth: `spec.md` (approved 2026-10-01). Requirement IDs (R1–R10) and interface names refer to it. Every task:

- reads `spec.md` §2 (its requirements), §4 (interfaces) and §5 (defaults) before starting;
- touches **only** its "Files in scope";
- leaves `pytest tests/` and `cd frontend && npx vitest run && npx tsc --noEmit` green;
- adds no new runtime dependencies (spec default 13).

## Execution order

```
Wave 1:  T1 ─────────────┐        T5 (independent, TypeScript)
Wave 2:  T2   T3   T4    │        T6  (after T5)
Wave 3:  T7 (after T2,T3,T4)   T8 (after T4)   T9 (after T6)
Wave 4:  T10 (after T7, T8)
Wave 5:  T11 (after all)
```

Tasks within the same wave share no files.

---

### T1 — Shared models and test set
- **Goal:** Define the Python boundary models and write the 30-case test set, so every other Python task builds on fixed types and data.
- **Files in scope:**
  - `evals/__init__.py`
  - `evals/models.py`
  - `evals/cases.json`
  - `evals/fixtures/two_cases.json`
  - `tests/test_evals_cases.py`
- **Depends on:** none.
- **Done when:**
  - [ ] `evals/models.py` defines Pydantic models matching spec §4.1 exactly, with camelCase JSON aliases that serialize to the same field names as the TS interfaces: `ProductTag` / `DocSource` / `EvalCategory` literals, `EvalCase`, `CasesFile` (`version`, `cases`), `RuleResults`, `JudgeVerdict` (scores constrained to 1–5), `CaseResult`, `RunSummary`, the `Regression` discriminated union, and `EvalRunPayload`.
  - [ ] `evals/cases.json` meets R1: at least 30 cases in the required category mix. Every `expectedProductTag` is one of the tags listed in `prompt.py`, ids are unique kebab-case, and each case has 2–4 key points.
  - [ ] `evals/fixtures/two_cases.json` holds 2 valid cases for offline runs.
  - [ ] The tests cover:
    - the schema loads;
    - ids are unique;
    - the category minimums;
    - tags match the `prompt.py` list, parsed from the `product_tag must be exactly one of:` line, so a prompt change breaks the test;
    - the key-point count is in range;
    - `question` is at most 2000 characters.
  - [ ] Verify: `pytest tests/test_evals_cases.py -v`.
  - [ ] Human gate: the product owner reviews `evals/cases.json` in the PR before T7 merges.

### T2 — Rule checks
- **Goal:** Implement the five deterministic rule checks from R3.
- **Files in scope:** `evals/rules.py`, `tests/test_evals_rules.py`.
- **Depends on:** T1.
- **Done when:**
  - [ ] `evaluate_rules(case: EvalCase, response: str, chunks: list[dict], error: str | None) -> RuleResults` and `parse_product_tag(response: str) -> str | None` are implemented.
  - [ ] `citations` reuses `chat.find_unretrieved_doc_urls` and does not re-implement URL parsing. `retrieval` reads `chunk["source"]`.
  - [ ] For each of the 5 rules there is one passing and one failing fixture. Also covered: an error short-circuits every rule except `completed` to false, and `retrieval` passes when `expectedSources` is unset.
  - [ ] Verify: `pytest tests/test_evals_rules.py -v`.

### T3 — DeepSeek grader
- **Goal:** Implement the LLM grader from R4 behind `JUDGE_MODEL` / `JUDGE_BASE_URL`.
- **Files in scope:** `evals/judge.py`, `tests/test_evals_judge.py`.
- **Depends on:** T1.
- **Done when:**
  - [ ] `judge_case(case: EvalCase, response: str, chunks: list[dict], *, client: httpx.Client | None = None) -> tuple[JudgeVerdict | None, str | None]` returns `(verdict, judgeError)`.
  - [ ] It POSTs `{JUDGE_BASE_URL}/chat/completions` with:
    - `model` set to `JUDGE_MODEL` (default `deepseek-flash`);
    - `response_format: {"type": "json_object"}`;
    - `temperature: 0`;
    - `Authorization: Bearer $DEEPSEEK_API_KEY`;
    - a timeout of 60 s.
  - [ ] The prompt contains only the question, the key points, the retrieved chunk texts and the answer, and asks for the four `JudgeVerdict` fields as JSON.
  - [ ] The response is validated with Pydantic. Bad output gets one retry, then returns `(None, "invalid_output")`. HTTP or transport errors return `(None, "http_error: <status or class>")`. A missing key returns `(None, "missing_api_key")` and makes no request.
  - [ ] The API key is never logged.
  - [ ] Tests use `httpx.MockTransport` and cover: a valid verdict, invalid then valid, invalid twice, an out-of-range score, an HTTP 500, a missing key, and that the request body contains the chunk text and the key points.
  - [ ] Verify: `pytest tests/test_evals_judge.py -v`.

### T4 — Summary and regression detection
- **Goal:** Compute `RunSummary` and the regressions against a baseline (R5).
- **Files in scope:** `evals/regression.py`, `tests/test_evals_regression.py`.
- **Depends on:** T1.
- **Done when:**
  - [ ] It exposes `summarize(results: list[CaseResult]) -> RunSummary` and `find_regressions(current: list[CaseResult], summary: RunSummary, baseline: tuple[RunSummary, list[CaseResult]] | None, recent_best: float | None) -> list[Regression]`.
  - [ ] It defines the constants `MEAN_SCORE_DROP = 0.3`, `CASE_SCORE_DROP = 2`, `MAX_ERROR_RATE = 0.2` and `RECENT_BEST_DROP = 0.5`.
  - [ ] Case score is `(groundedness + coverage) / 2`. Ungraded cases are left out of the means. p50 and p95 use nearest-rank.
  - [ ] Tests cover:
    - the 5 regression kinds, including `recentBestDrop`;
    - a 0.2-per-week decline over 4 runs: `meanScoreDrop` never fires, but `recentBestDrop` fires by week 3;
    - `recent_best=None` skips (e);
    - no baseline returns `[]`;
    - a case missing from the baseline is ignored;
    - a mean drop of exactly 0.3 is not a regression;
    - an all-error run;
    - the summary maths on a hand-computed fixture.
  - [ ] Verify: `pytest tests/test_evals_regression.py -v`.

### T5 — Convex schema and ingest/baseline HTTP actions
- **Goal:** Store eval runs in Convex, behind HTTP endpoints protected by a shared secret (R6).
- **Files in scope:**
  - `frontend/convex/schema.ts`: add the two tables only.
  - `frontend/convex/http.ts` (new)
  - `frontend/convex/evalsIngest.ts` (new)
  - `frontend/convex/evals.harness.test.ts` (new)
  - `frontend/convex/_generated/` (codegen output only)
- **Depends on:** none.
- **Done when:**
  - [ ] `evalRuns` and `evalResults` match spec §4.2, including the `by_label_started`, `by_run` and `by_case` indexes. The existing tables are unchanged.
  - [ ] `http.ts` routes `POST /evals/runs` and `GET /evals/baseline`. Both compare the `Authorization` bearer with `process.env.EVAL_INGEST_SECRET` in constant time. A missing env var, header or match returns 401.
  - [ ] `evalsIngest.ts` holds an `internalMutation` `ingestRun` (inserts the run, then each result, and returns `runId`) and an `internalQuery` `latestScheduled` (the latest completed `scheduled` run with its results and `recentBestMeanScore`, the best `summary.meanScore` across the last 8 completed `scheduled` runs, or `null`).
  - [ ] The payload is validated: a bad shape returns 400 with `{ error }` and writes nothing.
  - [ ] `_generated/api.d.ts` includes the new modules. Regenerate with `npx convex codegen`; if that can't reach a deployment, hand-edit it to mirror the existing entries.
  - [ ] Tests use `convex-test` and `t.fetch`, and cover: 401 on no bearer, 401 on a wrong bearer, 400 on a bad payload, a 200 that writes 1 run plus N results, a baseline that returns the newest completed scheduled run (ignoring `manual` and `errored` runs), `recentBestMeanScore` taken from only the last 8 scheduled runs (a 9th, older, higher run is ignored), and a baseline of `null` when empty.
  - [ ] Verify: `cd frontend && npx vitest run convex/ && npx tsc --noEmit`.

### T6 — Admin-guarded Convex queries
- **Goal:** Add the read queries the dashboard uses, restricted to `EVAL_ADMIN_IDS` (R10).
- **Files in scope:**
  - `frontend/convex/evals.ts`: append only, leaving `createEval` and `setFeedback` untouched.
  - `frontend/convex/evals.admin.test.ts` (new)
  - `frontend/convex/_generated/` (codegen only)
- **Depends on:** T5.
- **Done when:**
  - [ ] It adds `amIAdmin`, `listRuns({ limit?: number ≤ 60, label? })` and `getRun({ runId: v.id('evalRuns') })`, the last returning `{ run, results, previous }` where `previous` is the prior completed `scheduled` run.
  - [ ] An `isAdmin(ctx)` helper parses `process.env.EVAL_ADMIN_IDS` as comma-separated and trimmed, and matches `identity.tokenIdentifier`. With no identity or no match, `listRuns` and `getRun` throw `Forbidden` and `amIAdmin` returns false.
  - [ ] Tests cover: guest → forbidden; a non-admin user → forbidden; an admin → data; `limit` capped at 60; `previous` correct, including `null` for the first run. The existing `evals.test.ts` still passes.
  - [ ] Verify: `cd frontend && npx vitest run convex/ && npx tsc --noEmit`.

### T7 — Convex client, runner and `make eval`
- **Goal:** Run the whole harness from the CLI: run the pipeline, apply the rules, grade, summarize, fetch the baseline, upload and report (R2, R7).
- **Files in scope:**
  - `evals/convex_client.py`
  - `evals/run.py`
  - `evals/report.py`
  - `Makefile`: add an `eval` target only.
  - `tests/test_evals_run.py`
- **Depends on:** T2, T3, T4. It uses T5's endpoint contract from the spec; T5 does not need to be merged to run the tests.
- **Done when:**
  - [ ] `python -m evals.run` supports `--label {scheduled,manual}` (default `manual`), `--cases`, `--out` (default `eval-out/`), `--no-upload`, `--dry-judge` and `--concurrency` (default 3), as in spec §4.3.
  - [ ] Each case calls `chat.stream_run(question, [])` and consumes the events up to `done`. Exceptions are recorded as `error` and the run continues.
  - [ ] When `EVAL_FAKE_PIPELINE=1`, a deterministic stub answer is used. `--dry-judge` returns a fixed verdict, so offline runs make no network calls.
  - [ ] `convex_client.py` provides `fetch_baseline() -> (RunSummary, list[CaseResult], recent_best: float | None) | None` and `upload(payload) -> runId` over `httpx`, using `CONVEX_SITE_URL` and `EVAL_INGEST_SECRET`. It passes `recent_best` through to `find_regressions`. If baseline fetching fails, the run continues with "no baseline" and a warning.
  - [ ] It writes `eval-out/run.json` (an `EvalRunPayload`, with `runId` added after upload) and `eval-out/report.md` (summary, regressions, worst 5 cases), and prints the report.
  - [ ] Exit codes: 0 = clean, 2 = regressions, 1 = harness error.
  - [ ] `gitSha` and `gitRef` come from `GITHUB_SHA` / `GITHUB_REF_NAME`, falling back to `git rev-parse`.
  - [ ] `make eval` runs `python -m evals.run --label manual`.
  - [ ] Tests cover: an offline run of the 2-case fixture that exits 0 and writes both files; a pipeline exception recorded with the run continuing; the upload called with the correct bearer (mocked); `--no-upload` making no calls; and exit 2 when a fake baseline produces a regression.
  - [ ] Verify: `EVAL_FAKE_PIPELINE=1 python -m evals.run --cases evals/fixtures/two_cases.json --no-upload --dry-judge; echo $?` prints `0`, and `pytest tests/test_evals_run.py -v` passes.

### T8 — Regression notifier
- **Goal:** Open an `eval-regression` GitHub issue, or comment on the open one (R9).
- **Files in scope:** `evals/notify.py`, `tests/test_evals_notify.py`.
- **Depends on:** T4.
- **Done when:**
  - [ ] `python -m evals.notify --run eval-out/run.json --run-url <url> [--dashboard-url <url>] [--harness-error]` does nothing when there are no regressions and no harness error.
  - [ ] Otherwise it uses the `gh` CLI through `subprocess`, passing `GH_TOKEN` via env:
    1. `gh issue list --label eval-regression --state open --json number --limit 1`;
    2. `gh issue comment <n>` if one is open;
    3. otherwise `gh issue create --label eval-regression`, creating the label first if it's missing.
  - [ ] The body is built by a pure `format_body(payload, run_url, dashboard_url) -> str`: a summary table, one line per regression (with case ids and before → after), and links.
  - [ ] Tests cover `format_body` snapshots for each regression kind and for a harness error, plus create-vs-comment decided against a stubbed `subprocess.run`. Inputs are never interpolated into a shell string (use list args).
  - [ ] Verify: `pytest tests/test_evals_notify.py -v`.

### T9 — `/evals` dashboard
- **Goal:** Build the admin dashboard: score trend, run list and case detail with deltas (R10).
- **Files in scope:**
  - `frontend/src/main.tsx`: add the `/evals` pathname branch only.
  - `frontend/vercel.json`: add the SPA rewrite.
  - `frontend/src/evals/` (new directory: components, hooks, styles)
  - `frontend/tests/evalsDashboard.test.ts`
  - `frontend/e2e/evals.spec.ts`
- **Depends on:** T6.
- **Done when:**
  - [ ] When `window.location.pathname === '/evals'`, `main.tsx` renders `<EvalsApp/>` inside the same Clerk/Convex providers. Every other path renders as today.
  - [ ] `vercel.json` gains `"rewrites": [{ "source": "/((?!assets/).*)", "destination": "/index.html" }]`, and the existing build settings are unchanged.
  - [ ] `EvalsApp` behaves as follows:
    - signed out or not an admin: shows "You don't have access to evals." and makes no data queries beyond `amIAdmin`;
    - admin: shows the trend (inline SVG, mean score and rule pass rate, last 26 scheduled runs), the run list, and the selected run's case table;
    - an expanded case shows the answer, the rule results, the grader's reason, the missed key points, and the change from `previous`.
  - [ ] A test seam mirrors the one in `useHistory.ts`: in the bypass build (`VITE_TEST_BYPASS_AUTH`), data comes from `window.__GOLEM_E2E_EVALS__` and admin is true.
  - [ ] Uses the existing tokens and type from `globals.css`. Follow the `frontend-design` skill for layout and the `dataviz` skill for the chart. No new dependencies.
  - [ ] Accessibility:
    - the chart has a text alternative (an `aria-label` with the latest value and trend direction, plus a visually hidden data table);
    - case rows are expandable with the keyboard;
    - status is never conveyed by colour alone.
  - [ ] Unit tests (with Convex hooks mocked) cover: the no-access view, the admin view rendering the trend and the run list, a case delta shown correctly, and the empty state ("No eval runs yet. Run `make eval`.").
  - [ ] E2E covers: `/evals` loads in the bypass build with seeded data, expanding a case works, and axe is clean in light and dark at desktop and 375 px.
  - [ ] Verify: `cd frontend && npx tsc --noEmit && npx vitest run tests/evalsDashboard.test.ts && npx playwright test e2e/evals.spec.ts`, then attach a screenshot of `/evals` with seeded data in both themes.

### T10 — Weekly workflow
- **Goal:** Schedule the harness weekly and wire up the notifier (R8, R9).
- **Files in scope:** `.github/workflows/eval-weekly.yml`.
- **Depends on:** T7, T8.
- **Done when:**
  - [ ] Triggers are `schedule: cron "0 6 * * 0"` and `workflow_dispatch` only, with no `pull_request` or `push`.
  - [ ] `permissions: { contents: read, issues: write }`. `concurrency: eval-weekly`. Timeout 30 minutes.
  - [ ] Steps:
    1. checkout `main`;
    2. set up Python 3.11;
    3. `pip install -r requirements.txt`;
    4. `python -m evals.run --label scheduled` with secrets passed through `env:` only;
    5. capture the exit code;
    6. upload `eval-out/` as an artifact (always);
    7. run `python -m evals.notify` when the exit code is 2 (regression) or 1 (with `--harness-error`);
    8. fail the job only on exit 1.
  - [ ] No secret or event field is interpolated into a `run:` script.
  - [ ] Verify: `actionlint .github/workflows/eval-weekly.yml` (`brew install actionlint`). After merge and after secrets are set, run `gh workflow run eval-weekly.yml` and attach the run URL showing a green run and the artifact.

### T11 — Docs, env and secrets
- **Goal:** Document how to run and operate the harness, and mark V3a done.
- **Files in scope:** `README.md`, `.env.example`.
- **Depends on:** T1–T10.
- **Done when:**
  - [ ] `.env.example` adds `DEEPSEEK_API_KEY`, `CONVEX_SITE_URL`, `EVAL_INGEST_SECRET`, and the optional `JUDGE_MODEL` / `JUDGE_BASE_URL`, with comments.
  - [ ] The README covers:
    - a "Running evals" subsection under "Running locally" (`make eval`, `--no-upload`, what the exit codes mean);
    - the one-time setup: GitHub secrets, `npx convex env set EVAL_INGEST_SECRET …` and `EVAL_ADMIN_IDS …`, and how to find your `tokenIdentifier`;
    - a V3a features table with V3a marked ✅ in the V3 roadmap;
    - the measured cost per run, taken from the first real run;
    - a note that GitHub disables scheduled workflows on public repos after 60 days without repo activity, so check the workflow's status (`gh workflow view eval-weekly.yml`) and re-enable it with `gh workflow enable eval-weekly.yml`.
  - [ ] Verify: `grep -n "make eval" README.md && grep -n "DEEPSEEK_API_KEY" .env.example`, plus the reviewer reads the setup steps end to end.
