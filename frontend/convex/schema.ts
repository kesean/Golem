import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  history: defineTable({
    userId: v.string(),
    question: v.string(),
    rawXml: v.string(),
  }).index("by_user", ["userId"]),
});
