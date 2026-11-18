import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const MAX_QUESTION_CHARS = 8000;
const MAX_RESPONSE_CHARS = 100_000;
// Per user, over a rolling 24h window. Only the newest MAX_CREATES_PER_DAY
// rows are read, so the check stays bounded however large the table grows.
const MAX_CREATES_PER_DAY = 200;
const DAY_MS = 24 * 60 * 60 * 1000;

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
    if (args.question.length > MAX_QUESTION_CHARS) {
      throw new Error("Question is too long");
    }
    if (args.response.length > MAX_RESPONSE_CHARS) {
      throw new Error("Response is too long");
    }

    const userId = identity.tokenIdentifier;
    const since = Date.now() - DAY_MS;
    const newest = await ctx.db
      .query("evals")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("desc")
      .take(MAX_CREATES_PER_DAY);
    const createdToday = newest.filter((row) => row._creationTime >= since).length;
    if (createdToday >= MAX_CREATES_PER_DAY) {
      throw new Error("Daily eval limit reached");
    }

    return await ctx.db.insert("evals", {
      userId,
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

const MAX_LIST_LIMIT = 60;

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

    // Clamp limit to [1, MAX_LIST_LIMIT]; default to the max when omitted
    const n = Math.max(1, Math.min(args.limit ?? MAX_LIST_LIMIT, MAX_LIST_LIMIT));

    // Newest first by startedAt, straight off an index
    if (args.label) {
      const label = args.label;
      return await ctx.db
        .query("evalRuns")
        .withIndex("by_label_started", (q) => q.eq("label", label))
        .order("desc")
        .take(n);
    }
    return await ctx.db
      .query("evalRuns")
      .withIndex("by_started")
      .order("desc")
      .take(n);
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

    // Find the prior completed scheduled run (baseline), for scheduled and manual runs alike
    let previous = null;
    const previousRun = await ctx.db
      .query("evalRuns")
      .withIndex("by_label_started", (q) =>
        q.eq("label", "scheduled" as const).lt("startedAt", run.startedAt)
      )
      .order("desc")
      .filter((q) => q.eq(q.field("status"), "completed"))
      .first();
    if (previousRun) {
      const previousResults = await ctx.db
        .query("evalResults")
        .withIndex("by_run", (q) => q.eq("runId", previousRun._id))
        .collect();
      previous = { run: previousRun, results: previousResults };
    }

    return { run, results, previous };
  },
});
