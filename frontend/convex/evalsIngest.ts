import { internalMutation, internalQuery } from "./_generated/server";
import { v } from "convex/values";

export const ingestRun = internalMutation({
  args: {
    run: v.object({
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
      baselineRunId: v.optional(v.string()),
    }),
    results: v.array(
      v.object({
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
          v.union(
            v.null(),
            v.object({
              groundedness: v.number(),
              coverage: v.number(),
              keyPointsMissed: v.array(v.string()),
              reason: v.string(),
            })
          )
        ),
        judgeError: v.optional(v.string()),
        latencyMs: v.number(),
        inputTokens: v.number(),
        outputTokens: v.number(),
        error: v.optional(v.string()),
      })
    ),
  },
  handler: async (ctx, args) => {
    // Process baselineRunId: normalize it if provided, else omit
    const runData: typeof args.run & { baselineRunId?: string } = {
      ...args.run,
    };

    if (args.run.baselineRunId) {
      try {
        const normalized = ctx.db.normalizeId("evalRuns", args.run.baselineRunId);
        if (normalized) {
          runData.baselineRunId = normalized;
        } else {
          delete runData.baselineRunId;
        }
      } catch {
        // If normalization fails, omit the field
        delete runData.baselineRunId;
      }
    } else {
      delete runData.baselineRunId;
    }

    // Insert the run
    const runId = await ctx.db.insert("evalRuns", runData as any);

    // Insert results
    for (const result of args.results) {
      const resultData: any = {
        runId,
        caseId: result.caseId,
        question: result.question,
        response: result.response,
        retrievedUrls: result.retrievedUrls,
        rules: result.rules,
        latencyMs: result.latencyMs,
        inputTokens: result.inputTokens,
        outputTokens: result.outputTokens,
      };

      if (result.productTag !== undefined) {
        resultData.productTag = result.productTag;
      }
      if (result.judge !== undefined) {
        resultData.judge = result.judge;
      }
      if (result.judgeError !== undefined) {
        resultData.judgeError = result.judgeError;
      }
      if (result.error !== undefined) {
        resultData.error = result.error;
      }

      await ctx.db.insert("evalResults", resultData);
    }

    return runId;
  },
});

export const latestScheduled = internalQuery({
  args: {},
  handler: async (ctx) => {
    // Get all scheduled runs, filter for completed, and sort to get the latest
    const allRuns = await ctx.db
      .query("evalRuns")
      .withIndex("by_label_started", (q) =>
        q.eq("label", "scheduled")
      )
      .collect();

    const completedRuns = allRuns
      .filter((run) => run.status === "completed")
      .sort((a, b) => b.startedAt - a.startedAt);

    if (completedRuns.length === 0) {
      return null;
    }

    const run = completedRuns[0];

    // Get all results for this run
    const results = await ctx.db
      .query("evalResults")
      .withIndex("by_run", (q) => q.eq("runId", run._id))
      .collect();

    // Get the last 8 completed scheduled runs to calculate recentBestMeanScore
    const recentRuns = completedRuns.slice(0, 8);
    const recentBestMeanScore =
      recentRuns.length > 0
        ? Math.max(...recentRuns.map((r) => r.summary.meanScore))
        : 0;

    return {
      run,
      results,
      recentBestMeanScore,
    };
  },
});
