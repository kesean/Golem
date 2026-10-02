/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test, beforeEach, afterEach } from "vitest";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

// Setup and teardown for EVAL_INGEST_SECRET
beforeEach(() => {
  process.env.EVAL_INGEST_SECRET = "test-secret";
});

afterEach(() => {
  delete process.env.EVAL_INGEST_SECRET;
});

// Helper function to create valid payload
function validPayload() {
  return {
    run: {
      label: "scheduled" as const,
      gitSha: "abc123",
      gitRef: "main",
      appModel: "claude-sonnet-5",
      judgeModel: "deepseek-flash",
      casesVersion: 1,
      startedAt: Date.now(),
      finishedAt: Date.now() + 1000,
      status: "completed" as const,
      summary: {
        caseCount: 2,
        gradedCount: 2,
        errorCount: 0,
        meanGroundedness: 4.5,
        meanCoverage: 4.0,
        meanScore: 4.25,
        rulePassRate: {
          completed: 1.0,
          format: 1.0,
          productTag: 0.5,
          citations: 1.0,
          retrieval: 0.5,
        },
        p50LatencyMs: 1000,
        p95LatencyMs: 2000,
        totalInputTokens: 100,
        totalOutputTokens: 200,
      },
      regressions: [],
      baselineRunId: null,
    },
    results: [
      {
        caseId: "case-1",
        question: "What is CORS?",
        response: "<summary>CORS is...</summary>",
        productTag: "CORS",
        retrievedUrls: ["https://mdn.org"],
        rules: {
          completed: true,
          format: true,
          productTag: true,
          citations: true,
          retrieval: true,
        },
        judge: {
          groundedness: 5,
          coverage: 4,
          keyPointsMissed: [],
          reason: "Good answer.",
        },
        latencyMs: 1000,
        inputTokens: 50,
        outputTokens: 100,
      },
      {
        caseId: "case-2",
        question: "How do I handle 401?",
        response: "<summary>401 means...</summary>",
        productTag: "Authentication",
        retrievedUrls: ["https://clerk.com"],
        rules: {
          completed: true,
          format: true,
          productTag: false,
          citations: true,
          retrieval: true,
        },
        judge: {
          groundedness: 4,
          coverage: 4,
          keyPointsMissed: ["some detail"],
          reason: "Mostly good.",
        },
        latencyMs: 1000,
        inputTokens: 50,
        outputTokens: 100,
      },
    ],
  };
}

// ── Authorization tests ────────────────────────────────────────────────────

test("POST /evals/runs returns 401 with no bearer header", async () => {
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(validPayload()),
    headers: { "Content-Type": "application/json" },
  });
  expect(response.status).toBe(401);
});

test("POST /evals/runs returns 401 with wrong bearer token", async () => {
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(validPayload()),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer wrong-secret",
    },
  });
  expect(response.status).toBe(401);
});

test("POST /evals/runs returns 401 when env var unset", async () => {
  delete process.env.EVAL_INGEST_SECRET;
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(validPayload()),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(401);
});

test("GET /evals/baseline returns 401 with no bearer header", async () => {
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/baseline");
  expect(response.status).toBe(401);
});

test("GET /evals/baseline returns 401 with wrong bearer token", async () => {
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/baseline", {
    headers: { Authorization: "Bearer wrong-secret" },
  });
  expect(response.status).toBe(401);
});

test("GET /evals/baseline returns 401 when env var unset", async () => {
  delete process.env.EVAL_INGEST_SECRET;
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/baseline", {
    headers: { Authorization: "Bearer test-secret" },
  });
  expect(response.status).toBe(401);
});

// ── Payload validation tests ────────────────────────────────────────────────

test("POST /evals/runs returns 400 on missing run.label", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  delete (payload.run as any).label;

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs returns 400 on invalid JSON", async () => {
  const t = convexTest(schema, modules);

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: "{ invalid json",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs returns 400 on invalid regression kind", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  payload.run.regressions = [
    { kind: "invalidKind", foo: "bar" },
  ];

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs returns 400 when casesVersion is a string", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  (payload.run as any).casesVersion = "1";

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs returns 400 when summary.meanScore is a string", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  (payload.run.summary as any).meanScore = "4.25";

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs returns 400 when result.latencyMs is a string", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  (payload.results[0] as any).latencyMs = "1000";

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

// ── Successful write ────────────────────────────────────────────────────────

test("POST /evals/runs writes 1 run and 2 results on valid payload", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data.runId).toBeDefined();
  expect(typeof data.runId).toBe("string");

  // Verify the run was inserted
  const runId = data.runId;
  const run = await t.run(async (ctx) => ctx.db.get(runId));
  expect(run).toBeDefined();
  expect(run?.label).toBe("scheduled");
  expect(run?.summary.caseCount).toBe(2);

  // Verify results were inserted
  const results = await t.run(async (ctx) =>
    ctx.db
      .query("evalResults")
      .withIndex("by_run", (q) => q.eq("runId", runId))
      .collect()
  );
  expect(results.length).toBe(2);
  expect(results[0].caseId).toBe("case-1");
  expect(results[1].caseId).toBe("case-2");
});

// ── Null field normalization ────────────────────────────────────────────────

test("POST /evals/runs stores docs with null optional fields omitted", async () => {
  const t = convexTest(schema, modules);
  const payload = validPayload();
  payload.run.baselineRunId = null;
  payload.results[0].productTag = null;
  payload.results[0].judge = null;
  payload.results[1].judgeError = null;
  payload.results[1].error = null;

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const { runId } = await response.json();

  // Verify run doesn't have baselineRunId
  const run = await t.run(async (ctx) => ctx.db.get(runId));
  expect(run?.baselineRunId).toBeUndefined();

  // Verify results have null fields omitted
  const results = await t.run(async (ctx) =>
    ctx.db
      .query("evalResults")
      .withIndex("by_run", (q) => q.eq("runId", runId))
      .collect()
  );
  expect(results[0].productTag).toBeUndefined();
  expect(results[0].judge).toBeUndefined();
  expect(results[1].judgeError).toBeUndefined();
  expect(results[1].error).toBeUndefined();
});

// ── Baseline endpoint ──────────────────────────────────────────────────────

test("GET /evals/baseline returns null when no runs exist", async () => {
  const t = convexTest(schema, modules);

  const response = await t.fetch("/evals/baseline", {
    headers: {
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data).toBeNull();
});

test("GET /evals/baseline returns latest completed scheduled run, ignoring manual and errored", async () => {
  const t = convexTest(schema, modules);

  // Insert a manual run with high score (newer) - should be ignored
  const manualPayload = validPayload();
  manualPayload.run.label = "manual";
  manualPayload.run.startedAt = Date.now() + 5000;
  manualPayload.run.summary.meanScore = 5.0;

  await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(manualPayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });

  // Insert an errored run with high score (newer) - should be ignored
  const erroredPayload = validPayload();
  erroredPayload.run.status = "errored";
  erroredPayload.run.startedAt = Date.now() + 3000;
  erroredPayload.run.summary.meanScore = 4.8;

  await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(erroredPayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });

  // Insert the baseline scheduled run (oldest, lowest score)
  const baselinePayload = validPayload();
  baselinePayload.run.label = "scheduled";
  baselinePayload.run.startedAt = Date.now() - 1000;
  baselinePayload.run.summary.meanScore = 4.25;

  await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(baselinePayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });

  const response = await t.fetch("/evals/baseline", {
    headers: {
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();
  expect(data).not.toBeNull();
  expect(data.run.label).toBe("scheduled");
  expect(data.run.status).toBe("completed");
  expect(data.run.summary.meanScore).toBe(4.25); // Not the manual or errored
  expect(data.results.length).toBe(2);
  // recentBestMeanScore should be 4.25 (the only scheduled run)
  expect(data.recentBestMeanScore).toBe(4.25);
});

test("GET /evals/baseline limits recentBestMeanScore to last 8 runs", async () => {
  const t = convexTest(schema, modules);

  // Insert 9 scheduled runs with scores [9,1,2,3,4,3,2,1,2]
  // The oldest run (score 9) should not be included in the best-of-8
  const scores = [9, 1, 2, 3, 4, 3, 2, 1, 2]; // oldest to newest
  for (let i = 0; i < scores.length; i++) {
    const payload = validPayload();
    payload.run.startedAt = Date.now() - (scores.length - i) * 1000;
    payload.run.summary.meanScore = scores[i];
    await t.fetch("/evals/runs", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer test-secret",
      },
    });
  }

  const response = await t.fetch("/evals/baseline", {
    headers: {
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();
  // Latest run has score 2, the last 8 runs have scores [1,2,3,4,3,2,1,2]
  // Best of those is 4, not the 9 from the oldest run
  expect(data.recentBestMeanScore).toBe(4);
});

test("POST /evals/runs handles baselineRunId normalization", async () => {
  const t = convexTest(schema, modules);

  // First, create a baseline run
  const baselinePayload = validPayload();
  const baselineResponse = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(baselinePayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  const { runId: baselineRunId } = await baselineResponse.json();

  // Now create a new run with the baseline ID
  const newPayload = validPayload();
  newPayload.run.startedAt = Date.now() + 1000;
  newPayload.run.baselineRunId = baselineRunId;

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(newPayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();

  // Verify the new run has the baseline ID set
  const newRun = await t.run(async (ctx) => ctx.db.get(data.runId));
  expect(newRun?.baselineRunId).toBe(baselineRunId);
});

test("POST /evals/runs validates regression meanScoreDrop", async () => {
  const t = convexTest(schema, modules);

  const payload = validPayload();
  payload.run.regressions = [
    {
      kind: "meanScoreDrop",
      baseline: 4.5,
      current: 4.0,
    },
  ];

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
});

test("POST /evals/runs validates regression ruleFlip", async () => {
  const t = convexTest(schema, modules);

  const payload = validPayload();
  payload.run.regressions = [
    {
      kind: "ruleFlip",
      caseId: "case-1",
      rule: "format",
    },
  ];

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
});

test("POST /evals/runs rejects invalid rule in ruleFlip", async () => {
  const t = convexTest(schema, modules);

  const payload = validPayload();
  payload.run.regressions = [
    {
      kind: "ruleFlip",
      caseId: "case-1",
      rule: "invalidRule",
    },
  ];

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
});

test("POST /evals/runs rejects results with missing rules fields", async () => {
  const t = convexTest(schema, modules);

  const payload = validPayload();
  delete (payload.results[0].rules as any).format;

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const data = await response.json();
  expect(data.error).toBeDefined();

  // Verify nothing was written
  const runs = await t.run(async (ctx) => ctx.db.query("evalRuns").collect());
  expect(runs.length).toBe(0);
});

test("POST /evals/runs handles results with optional error field", async () => {
  const t = convexTest(schema, modules);

  const payload = validPayload();
  (payload.results[0] as any).error = "Some error occurred";

  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(200);
  const data = await response.json();

  const results = await t.run(async (ctx) =>
    ctx.db
      .query("evalResults")
      .withIndex("by_run", (q) => q.eq("runId", data.runId))
      .collect()
  );
  expect(results[0].error).toBe("Some error occurred");
});
