/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { internal } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

const SUMMARY = {
  caseCount: 1,
  gradedCount: 1,
  errorCount: 0,
  meanGroundedness: 4,
  meanCoverage: 4,
  meanScore: 4,
  rulePassRate: { completed: 1, format: 1, productTag: 1, citations: 1, retrieval: 1 },
  p50LatencyMs: 100,
  p95LatencyMs: 200,
  totalInputTokens: 10,
  totalOutputTokens: 20,
};

function runDoc(overrides: Partial<{
  label: "scheduled" | "manual";
  status: "completed" | "errored";
  startedAt: number;
  gitSha: string;
  meanScore: number;
}> = {}) {
  const { meanScore, ...rest } = overrides;
  return {
    label: "scheduled" as const,
    gitSha: "sha-a",
    gitRef: "main",
    appModel: "app-model",
    judgeModel: "judge-model",
    casesVersion: 1,
    startedAt: 1_000,
    finishedAt: 2_000,
    status: "completed" as const,
    summary: { ...SUMMARY, meanScore: meanScore ?? 4 },
    regressions: [],
    ...rest,
  };
}

// ── latestScheduled ───────────────────────────────────────────────────────────

test("latestScheduled returns null when no completed scheduled run exists", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    await ctx.db.insert("evalRuns", runDoc({ label: "manual" }));
    await ctx.db.insert("evalRuns", runDoc({ status: "errored" }));
  });
  expect(await t.query(internal.evalsIngest.latestScheduled, {})).toBeNull();
});

test("latestScheduled picks the newest completed scheduled run, ignoring manual and errored", async () => {
  const t = convexTest(schema, modules);
  let newestId: any;
  await t.run(async (ctx) => {
    await ctx.db.insert("evalRuns", runDoc({ startedAt: 1_000 }));
    newestId = await ctx.db.insert("evalRuns", runDoc({ startedAt: 2_000 }));
    await ctx.db.insert("evalRuns", runDoc({ startedAt: 3_000, label: "manual" }));
    await ctx.db.insert("evalRuns", runDoc({ startedAt: 4_000, status: "errored" }));
  });
  const result = await t.query(internal.evalsIngest.latestScheduled, {});
  expect(result?.run._id).toBe(newestId);
});

test("latestScheduled takes recentBestMeanScore from the newest 8 completed runs only", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    // Oldest run has the best score but falls outside the newest 8.
    await ctx.db.insert("evalRuns", runDoc({ startedAt: 1_000, meanScore: 4.9 }));
    for (let i = 0; i < 8; i++) {
      await ctx.db.insert("evalRuns", runDoc({ startedAt: 2_000 + i, meanScore: 3 + i * 0.1 }));
    }
  });
  const result = await t.query(internal.evalsIngest.latestScheduled, {});
  expect(result?.recentBestMeanScore).toBeCloseTo(3.7);
});
