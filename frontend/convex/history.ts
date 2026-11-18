import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Bounds. Oversized questions and answers are rejected outright. At the
// per-user row cap the OLDEST row is evicted to make room, so the newest
// answer is always saved. Eviction breaks any share link that points at the
// evicted row, which then shows the "link doesn't work" notice.
const MAX_QUESTION_CHARS = 8000;
const MAX_RAW_XML_CHARS = 100_000;
const MAX_ROWS_PER_USER = 200;
const LIST_LIMIT = 100;

// Public — no auth required, used for shareable links. Takes a typed
// history ID (rejects IDs from other tables) and returns only the fields a
// share view needs, never the owner's userId.
export const getById = query({
  args: { id: v.id("history") },
  handler: async (ctx, args) => {
    const entry = await ctx.db.get(args.id);
    if (!entry) return null;
    return { question: entry.question, rawXml: entry.rawXml };
  },
});

export const list = query({
  args: {},
  handler: async (ctx) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    return await ctx.db
      .query("history")
      .withIndex("by_user", (q) => q.eq("userId", identity.tokenIdentifier))
      .order("desc")
      .take(LIST_LIMIT);
  },
});

export const add = mutation({
  args: {
    question: v.string(),
    rawXml: v.string(),
  },
  handler: async (ctx, args) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    if (args.question.length > MAX_QUESTION_CHARS) {
      throw new Error("Question is too long");
    }
    if (args.rawXml.length > MAX_RAW_XML_CHARS) {
      throw new Error("Answer is too long");
    }

    // Make room from the oldest end. Normally this evicts at most one row;
    // a user already over the cap (legacy rows) loses one row per add until
    // back under it.
    const userId = identity.tokenIdentifier;
    const oldest = await ctx.db
      .query("history")
      .withIndex("by_user", (q) => q.eq("userId", userId))
      .order("asc")
      .take(MAX_ROWS_PER_USER);
    const excess = oldest.length - (MAX_ROWS_PER_USER - 1);
    for (const row of oldest.slice(0, Math.max(0, excess))) {
      await ctx.db.delete(row._id);
    }

    return await ctx.db.insert("history", {
      userId,
      question: args.question,
      rawXml: args.rawXml,
    });
  },
});

export const clear = mutation({
  args: {},
  handler: async (ctx) => {
    const identity = await ctx.auth.getUserIdentity();
    if (!identity) throw new Error("Unauthenticated");
    const entries = await ctx.db
      .query("history")
      .withIndex("by_user", (q) => q.eq("userId", identity.tokenIdentifier))
      .collect();
    await Promise.all(entries.map((e) => ctx.db.delete(e._id)));
  },
});
