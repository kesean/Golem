/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

beforeEach(() => {
  process.env.EVAL_INGEST_SECRET = "test-secret";
});

afterEach(() => {
  delete process.env.EVAL_INGEST_SECRET;
  vi.restoreAllMocks();
});

// Passes validatePayload, but the unknown run.extraField fails the Convex
// validator inside ingestRun, which is the branch under test.
function payloadFailingConvexValidator() {
  return {
    run: {
      label: "scheduled",
      gitSha: "sha-http",
      gitRef: "main",
      appModel: "app",
      judgeModel: "judge",
      casesVersion: 1,
      startedAt: 1,
      finishedAt: 2,
      status: "completed",
      summary: {
        caseCount: 0,
        gradedCount: 0,
        errorCount: 0,
        meanGroundedness: 0,
        meanCoverage: 0,
        meanScore: 0,
        rulePassRate: { completed: 0, format: 0, productTag: 0, citations: 0, retrieval: 0 },
        p50LatencyMs: 0,
        p95LatencyMs: 0,
        totalInputTokens: 0,
        totalOutputTokens: 0,
      },
      regressions: [],
      extraField: "internal-detail",
    },
    results: [],
  };
}

test("POST /evals/runs returns a generic 400 and logs the Convex validator detail", async () => {
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const t = convexTest(schema, modules);
  const response = await t.fetch("/evals/runs", {
    method: "POST",
    body: JSON.stringify(payloadFailingConvexValidator()),
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer test-secret",
    },
  });
  expect(response.status).toBe(400);
  const body = await response.text();
  expect(body).not.toContain("extraField");
  expect(body).not.toContain("Validator");
  expect(JSON.parse(body)).toEqual({ error: "Invalid payload" });
  const logged = errorSpy.mock.calls.map((args) => args.map(String).join(" ")).join("\n");
  expect(logged).toContain("extraField");
});
