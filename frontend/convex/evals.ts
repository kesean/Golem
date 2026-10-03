import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const createEval = mutation({
  args: {
    question: v.string(),
    response: v.string(),
    latency_ms: v.number(),
    input_tokens: v.number(),
    output_tokens: v.number(),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    return await ctx.db.insert("evals", {
      userId: identity.tokenIdentifier,
      question: args.question,
      response: args.response,
      latency_ms: args.latency_ms,
      input_tokens: args.input_tokens,
      output_tokens: args.output_tokens,
    });
  },
});

export const setFeedback = mutation({
  args: {
    evalId: v.id("evals"),
    feedback: v.optional(v.union(v.literal("up"), v.literal("down"))),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    const record = await ctx.db.get(args.evalId);
    if (!record || record.userId !== identity.tokenIdentifier) {
      throw new Error("Not found");
    }
    await ctx.db.patch(args.evalId, { feedback: args.feedback });
  },
});

// ── Admin-guarded queries ─────────────────────────────────────────────────

/**
 * Parse EVAL_ADMIN_IDS from environment and check if identity matches.
 * Returns true if the user is an admin, false otherwise.
 */
function isAdmin(ctx: any, identity: any): boolean {
  const adminIds = process.env.EVAL_ADMIN_IDS;
  if (!adminIds || !identity) return false;

  const adminList = adminIds
    .split(",")
    .map((id) => id.trim())
    .filter((id) => id.length > 0);

  return adminList.includes(identity.tokenIdentifier);
}

/**
 * Check if the current user is an admin.
 * Returns true if the user is in EVAL_ADMIN_IDS, false otherwise.
 */
export const amIAdmin = query({
  args: {},
  handler: async (ctx) => {
    const identity = await ctx.auth.getUserIdentity();
    return isAdmin(ctx, identity);
  },
});

/**
 * List eval runs, newest first by startedAt.
 * Only admins can access this query.
 * Throws Forbidden if user is not an admin.
 */
export const listRuns = query({
  args: {
    limit: v.optional(v.number()),
    label: v.optional(v.union(v.literal("scheduled"), v.literal("manual"))),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!isAdmin(ctx, identity)) {
      throw new Error("Forbidden");
    }

    // Cap limit at 60
    const limit = args.limit ? Math.min(args.limit, 60) : undefined;

    // Get runs - use index if label is specified
    const runs = await (args.label
      ? ctx.db
          .query("evalRuns")
          .withIndex("by_label_started", (q) =>
            q.eq("label", args.label as "scheduled" | "manual")
          )
          .collect()
      : ctx.db.query("evalRuns").collect());

    // Sort by startedAt descending (newest first)
    const sorted = runs.sort(
      (a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0)
    );

    if (limit) {
      return sorted.slice(0, limit);
    }
    return sorted;
  },
});

/**
 * Get a specific run by ID, including all its results and the previous scheduled run.
 * Only admins can access this query.
 * Throws Forbidden if user is not an admin.
 * Returns { run, results, previous } where previous is the most recent completed
 * scheduled run that started before this run (or null if none exists).
 */
export const getRun = query({
  args: {
    runId: v.id("evalRuns"),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!isAdmin(ctx, identity)) {
      throw new Error("Forbidden");
    }

    const run = await ctx.db.get(args.runId);
    if (!run) {
      throw new Error("Run not found");
    }

    // Get all results for this run
    const results = await ctx.db
      .query("evalResults")
      .withIndex("by_run", (q) => q.eq("runId", args.runId))
      .collect();

    // Find the previous completed scheduled run
    let previous = null;
    if (run.label === "scheduled") {
      // Get all scheduled runs using the index
      const allScheduledRuns = await ctx.db
        .query("evalRuns")
        .withIndex("by_label_started", (q) => q.eq("label", "scheduled" as const))
        .collect();

      // Filter for runs that started before this one and are completed
      const candidates = allScheduledRuns.filter(
        (r) => r.startedAt < run.startedAt && r.status === "completed"
      );

      // Sort by startedAt descending (most recent first)
      candidates.sort((a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0));

      if (candidates.length > 0) {
        const previousRun = candidates[0];
        const previousResults = await ctx.db
          .query("evalResults")
          .withIndex("by_run", (q) => q.eq("runId", previousRun._id))
          .collect();
        previous = { run: previousRun, results: previousResults };
      }
    }

    return { run, results, previous };
  },
});
