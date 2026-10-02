import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  history: defineTable({
    userId: v.string(),
    question: v.string(),
    rawXml: v.string(),
  }).index("by_user", ["userId"]),
  evals: defineTable({
    userId: v.string(),
    question: v.string(),
    response: v.string(),
    latency_ms: v.number(),
    input_tokens: v.number(),
    output_tokens: v.number(),
    feedback: v.optional(v.union(v.literal("up"), v.literal("down"))),
  }).index("by_user", ["userId"]),
  stats: defineTable({
    totalQuestions: v.number(),
  }),
  evalRuns: defineTable({
    label: v.union(v.literal("scheduled"), v.literal("manual")),
    gitSha: v.string(),
    gitRef: v.string(),
    appModel: v.string(),
    judgeModel: v.string(),
    casesVersion: v.number(),
    startedAt: v.number(),
    finishedAt: v.number(),
    status: v.union(v.literal("completed"), v.literal("errored")),
    summary: v.object({
      caseCount: v.number(),
      gradedCount: v.number(),
      errorCount: v.number(),
      meanGroundedness: v.number(),
      meanCoverage: v.number(),
      meanScore: v.number(),
      rulePassRate: v.object({
        completed: v.number(),
        format: v.number(),
        productTag: v.number(),
        citations: v.number(),
        retrieval: v.number(),
      }),
      p50LatencyMs: v.number(),
      p95LatencyMs: v.number(),
      totalInputTokens: v.number(),
      totalOutputTokens: v.number(),
    }),
    regressions: v.array(v.any()),
    baselineRunId: v.optional(v.id("evalRuns")),
  }).index("by_label_started", ["label", "startedAt"]),
  evalResults: defineTable({
    runId: v.id("evalRuns"),
    caseId: v.string(),
    question: v.string(),
    response: v.string(),
    productTag: v.optional(v.string()),
    retrievedUrls: v.array(v.string()),
    rules: v.object({
      completed: v.boolean(),
      format: v.boolean(),
      productTag: v.boolean(),
      citations: v.boolean(),
      retrieval: v.boolean(),
    }),
    judge: v.optional(
      v.object({
        groundedness: v.number(),
        coverage: v.number(),
        keyPointsMissed: v.array(v.string()),
        reason: v.string(),
      })
    ),
    judgeError: v.optional(v.string()),
    latencyMs: v.number(),
    inputTokens: v.number(),
    outputTokens: v.number(),
    error: v.optional(v.string()),
  })
    .index("by_run", ["runId"])
    .index("by_case", ["caseId"]),
});
