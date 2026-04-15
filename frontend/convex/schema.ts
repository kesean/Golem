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
});
