/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test, beforeEach, afterEach } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

// Setup and teardown for EVAL_ADMIN_IDS and EVAL_INGEST_SECRET
beforeEach(() => {
  process.env.EVAL_ADMIN_IDS = "admin|user1, admin|user2";
  process.env.EVAL_INGEST_SECRET = "test-secret";
});

afterEach(() => {
  delete process.env.EVAL_ADMIN_IDS;
  delete process.env.EVAL_INGEST_SECRET;
});

// ── Helper function to create valid evalRun payload ────────────────────────

function validPayload(overrides?: { label?: string; startedAt?: number }) {
  return {
    run: {
      label: overrides?.label ?? ("scheduled" as const),
      gitSha: "abc123",
      gitRef: "main",
      appModel: "claude-sonnet-5",
      judgeModel: "deepseek-flash",
      casesVersion: 1,
      startedAt: overrides?.startedAt ?? Date.now(),
      finishedAt: (overrides?.startedAt ?? Date.now()) + 1000,
      status: "completed" as const,
      summary: {
        caseCount: 1,
        gradedCount: 1,
        errorCount: 0,
        meanGroundedness: 4.5,
        meanCoverage: 4.0,
        meanScore: 4.25,
        rulePassRate: {
          completed: 1.0,
          format: 1.0,
          productTag: 1.0,
          citations: 1.0,
          retrieval: 1.0,
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
    ],
  };
}

async function insertRun(
  t: any,
  overrides?: { label?: string; startedAt?: number }
) {
  const payload = validPayload(overrides);
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
  return data.runId;
}

// ── amIAdmin tests ────────────────────────────────────────────────────────

test("amIAdmin returns false for guest (no identity)", async () => {
  const t = convexTest(schema, modules);
  const result = await t.query(api.evals.amIAdmin, {});
  expect(result).toBe(false);
});

test("amIAdmin returns false for non-admin user", async () => {
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "user|other" })
    .query(api.evals.amIAdmin, {});
  expect(result).toBe(false);
});

test("amIAdmin returns true for admin user (first admin in list)", async () => {
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.amIAdmin, {});
  expect(result).toBe(true);
});

test("amIAdmin returns true for admin user (second admin in list)", async () => {
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user2" })
    .query(api.evals.amIAdmin, {});
  expect(result).toBe(true);
});

test("amIAdmin returns false when EVAL_ADMIN_IDS not set", async () => {
  delete process.env.EVAL_ADMIN_IDS;
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.amIAdmin, {});
  expect(result).toBe(false);
});

test("amIAdmin handles whitespace in EVAL_ADMIN_IDS", async () => {
  process.env.EVAL_ADMIN_IDS = "  admin|user1  ,  admin|user2  ";
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.amIAdmin, {});
  expect(result).toBe(true);
});

// ── listRuns tests ────────────────────────────────────────────────────────

test("listRuns throws Forbidden for guest (no identity)", async () => {
  const t = convexTest(schema, modules);
  // Insert a run first
  await insertRun(t, { label: "scheduled", startedAt: Date.now() });

  await expect(t.query(api.evals.listRuns, { limit: 10 })).rejects.toThrow(
    "Forbidden"
  );
});

test("listRuns throws Forbidden for non-admin user", async () => {
  const t = convexTest(schema, modules);
  // Insert a run first
  await insertRun(t, { label: "scheduled", startedAt: Date.now() });

  await expect(
    t
      .withIdentity({ tokenIdentifier: "user|other" })
      .query(api.evals.listRuns, { limit: 10 })
  ).rejects.toThrow("Forbidden");
});

test("listRuns returns empty array when no runs exist", async () => {
  const t = convexTest(schema, modules);
  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, {});
  expect(result).toEqual([]);
});

test("listRuns returns runs for admin user", async () => {
  const t = convexTest(schema, modules);
  const runId = await insertRun(t, {
    label: "scheduled",
    startedAt: Date.now(),
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, {});
  expect(result.length).toBe(1);
  expect(result[0]._id).toBe(runId);
  expect(result[0].label).toBe("scheduled");
});

test("listRuns returns runs sorted newest first by startedAt", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  const runId1 = await insertRun(t, { label: "scheduled", startedAt: now });
  const runId2 = await insertRun(t, {
    label: "scheduled",
    startedAt: now + 5000,
  });
  const runId3 = await insertRun(t, {
    label: "scheduled",
    startedAt: now + 1000,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, {});
  expect(result.length).toBe(3);
  // Newest first
  expect(result[0]._id).toBe(runId2);
  expect(result[1]._id).toBe(runId3);
  expect(result[2]._id).toBe(runId1);
});

test("listRuns filters by label when provided", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  const scheduledId = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });
  const manualId = await insertRun(t, {
    label: "manual",
    startedAt: now + 1000,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, { label: "scheduled" });
  expect(result.length).toBe(1);
  expect(result[0]._id).toBe(scheduledId);
  expect(result[0].label).toBe("scheduled");
});

test("listRuns filters by label=manual", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  await insertRun(t, { label: "scheduled", startedAt: now });
  const manualId = await insertRun(t, {
    label: "manual",
    startedAt: now + 1000,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, { label: "manual" });
  expect(result.length).toBe(1);
  expect(result[0]._id).toBe(manualId);
});

test("listRuns respects limit parameter", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  for (let i = 0; i < 5; i++) {
    await insertRun(t, { label: "scheduled", startedAt: now + i * 1000 });
  }

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, { limit: 2 });
  expect(result.length).toBe(2);
});

test("listRuns caps limit at 60", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  // Insert 65 runs
  for (let i = 0; i < 65; i++) {
    await insertRun(t, {
      label: "scheduled",
      startedAt: now + i * 1000,
    });
  }

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, { limit: 100 });
  expect(result.length).toBe(60);
});

test("listRuns defaults to no limit if not specified (returns all within bounds)", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  for (let i = 0; i < 5; i++) {
    await insertRun(t, { label: "scheduled", startedAt: now + i * 1000 });
  }

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.listRuns, {});
  expect(result.length).toBe(5);
});

// ── getRun tests ────────────────────────────────────────────────────────

test("getRun throws Forbidden for guest (no identity)", async () => {
  const t = convexTest(schema, modules);
  const runId = await insertRun(t, {
    label: "scheduled",
    startedAt: Date.now(),
  });

  await expect(t.query(api.evals.getRun, { runId })).rejects.toThrow(
    "Forbidden"
  );
});

test("getRun throws Forbidden for non-admin user", async () => {
  const t = convexTest(schema, modules);
  const runId = await insertRun(t, {
    label: "scheduled",
    startedAt: Date.now(),
  });

  await expect(
    t
      .withIdentity({ tokenIdentifier: "user|other" })
      .query(api.evals.getRun, { runId })
  ).rejects.toThrow("Forbidden");
});

test("getRun returns run, results, and null previous for first run", async () => {
  const t = convexTest(schema, modules);
  const runId = await insertRun(t, {
    label: "scheduled",
    startedAt: Date.now(),
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId });

  expect(result.run._id).toBe(runId);
  expect(result.run.label).toBe("scheduled");
  expect(result.results.length).toBe(1);
  expect(result.results[0].caseId).toBe("case-1");
  expect(result.previous).toBeNull();
});

test("getRun finds previous completed scheduled run", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert first scheduled run
  const run1Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 2000,
  });

  // Insert a manual run (should be ignored as previous)
  await insertRun(t, { label: "manual", startedAt: now - 1000 });

  // Insert the current run
  const run2Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: run2Id });

  expect(result.run._id).toBe(run2Id);
  expect(result.previous).not.toBeNull();
  expect(result.previous?.run._id).toBe(run1Id);
  expect(result.previous?.run.label).toBe("scheduled");
  expect(result.previous?.results.length).toBe(1);
});

test("getRun ignores manual runs when finding previous", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert a scheduled run (old)
  const scheduledId = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 3000,
  });

  // Insert a manual run that comes after the scheduled run
  await insertRun(t, { label: "manual", startedAt: now - 1000 });

  // Insert the current scheduled run
  const currentId = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: currentId });

  expect(result.previous?.run._id).toBe(scheduledId);
});

test("getRun ignores errored runs when finding previous", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert a successful scheduled run
  const successId = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 3000,
  });

  // Insert an errored scheduled run
  const erroredPayload = validPayload({
    label: "scheduled",
    startedAt: now - 1000,
  });
  erroredPayload.run.status = "errored";
  await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(erroredPayload),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });

  // Insert the current scheduled run
  const currentId = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: currentId });

  expect(result.previous?.run._id).toBe(successId);
});

test("getRun finds most recent completed scheduled run before current run", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert multiple scheduled runs
  const run1Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 5000,
  });
  const run2Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 3000,
  });
  const run3Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 1000,
  });

  // Insert the current run
  const currentId = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: currentId });

  // Should find run3, not run2 or run1
  expect(result.previous?.run._id).toBe(run3Id);
});

test("getRun returns null previous for scheduled run with no earlier scheduled runs", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert a manual run
  await insertRun(t, { label: "manual", startedAt: now - 1000 });

  // Insert the current scheduled run (first scheduled run)
  const currentId = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: currentId });

  expect(result.previous).toBeNull();
});

test("getRun returns previous results alongside run", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();

  // Insert first scheduled run
  const run1Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now - 1000,
  });

  // Insert the current run
  const run2Id = await insertRun(t, {
    label: "scheduled",
    startedAt: now,
  });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: run2Id });

  expect(result.previous).not.toBeNull();
  expect(result.previous?.results.length).toBe(1);
  expect(result.previous?.results[0].caseId).toBe("case-1");
});

test("getRun gives a manual run the prior completed scheduled run as previous", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  await insertRun(t, { label: "scheduled", startedAt: now - 5000 });
  const scheduledId = await insertRun(t, { label: "scheduled", startedAt: now - 3000 });
  await insertRun(t, { label: "manual", startedAt: now - 2000 });
  const manualId = await insertRun(t, { label: "manual", startedAt: now });
  // A later scheduled run must not be picked.
  await insertRun(t, { label: "scheduled", startedAt: now + 1000 });

  const result = await t
    .withIdentity({ tokenIdentifier: "admin|user1" })
    .query(api.evals.getRun, { runId: manualId });

  expect(result.previous?.run._id).toBe(scheduledId);
});

test("listRuns clamps a non-positive limit to 1", async () => {
  const t = convexTest(schema, modules);
  const now = Date.now();
  for (let i = 0; i < 3; i++) {
    await insertRun(t, { label: "scheduled", startedAt: now + i * 1000 });
  }
  const asAdmin = t.withIdentity({ tokenIdentifier: "admin|user1" });
  expect((await asAdmin.query(api.evals.listRuns, { limit: 0 })).length).toBe(1);
  expect((await asAdmin.query(api.evals.listRuns, { limit: -5 })).length).toBe(1);
});
