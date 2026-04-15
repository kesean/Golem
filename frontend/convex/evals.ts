import { mutation } from "./_generated/server";
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
