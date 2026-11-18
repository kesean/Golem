/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

const ME = { tokenIdentifier: "test|user1", subject: "user1" };

test("getById returns question and rawXml without userId", async () => {
  const t = convexTest(schema, modules);
  let historyId: any;
  await t.run(async (ctx) => {
    historyId = await ctx.db.insert("history", {
      userId: "test|user1",
      question: "Q",
      rawXml: "<summary>ok</summary>",
    });
  });
  const result = await t.query(api.history.getById, { id: historyId });
  expect(result).toEqual({ question: "Q", rawXml: "<summary>ok</summary>" });
});

test("getById rejects an ID from another table", async () => {
  const t = convexTest(schema, modules);
  let evalId: any;
  await t.run(async (ctx) => {
    evalId = await ctx.db.insert("evals", {
      userId: "test|user1",
      question: "Q",
      response: "<summary>ok</summary>",
      latency_ms: 100,
      input_tokens: 10,
      output_tokens: 20,
    });
  });
  await expect(
    t.query(api.history.getById, { id: evalId as any })
  ).rejects.toThrow();
});

test("getById returns null for a deleted entry", async () => {
  const t = convexTest(schema, modules);
  let historyId: any;
  await t.run(async (ctx) => {
    historyId = await ctx.db.insert("history", {
      userId: "test|user1",
      question: "Q",
      rawXml: "<summary>ok</summary>",
    });
  });
  await t.run(async (ctx) => {
    await ctx.db.delete(historyId);
  });
  const result = await t.query(api.history.getById, { id: historyId });
  expect(result).toBeNull();
});

test("list returns only the caller's rows, newest first, capped at 100", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    for (let i = 0; i < 105; i++) {
      await ctx.db.insert("history", {
        userId: "test|user1",
        question: `Q${i}`,
        rawXml: "<summary>ok</summary>",
      });
    }
    await ctx.db.insert("history", {
      userId: "test|other",
      question: "not mine",
      rawXml: "<summary>ok</summary>",
    });
  });
  const rows = await t.withIdentity(ME).query(api.history.list, {});
  expect(rows).toHaveLength(100);
  expect(rows[0].question).toBe("Q104");
  expect(rows[99].question).toBe("Q5");
  expect(rows.every((r) => r.question !== "not mine")).toBe(true);
});

test("list requires an identity", async () => {
  const t = convexTest(schema, modules);
  await expect(t.query(api.history.list, {})).rejects.toThrow("Unauthenticated");
});

test("add rejects a question over 8000 characters and stores nothing", async () => {
  const t = convexTest(schema, modules);
  const me = t.withIdentity(ME);
  await expect(
    me.mutation(api.history.add, { question: "x".repeat(8001), rawXml: "<a/>" })
  ).rejects.toThrow("Question is too long");
  expect(await me.query(api.history.list, {})).toHaveLength(0);
});

test("add accepts a question of exactly 8000 characters", async () => {
  const t = convexTest(schema, modules);
  const me = t.withIdentity(ME);
  await me.mutation(api.history.add, { question: "x".repeat(8000), rawXml: "<a/>" });
  expect(await me.query(api.history.list, {})).toHaveLength(1);
});

test("add rejects an answer over 100000 characters and stores nothing", async () => {
  const t = convexTest(schema, modules);
  const me = t.withIdentity(ME);
  await expect(
    me.mutation(api.history.add, { question: "Q", rawXml: "x".repeat(100_001) })
  ).rejects.toThrow("Answer is too long");
  expect(await me.query(api.history.list, {})).toHaveLength(0);
});

test("add at the 200-row cap evicts the oldest row and keeps the newest", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    for (let i = 0; i < 200; i++) {
      await ctx.db.insert("history", {
        userId: "test|user1",
        question: `old${i}`,
        rawXml: "<summary>ok</summary>",
      });
    }
  });
  const me = t.withIdentity(ME);
  await me.mutation(api.history.add, { question: "newest", rawXml: "<a/>" });
  const rows = await me.query(api.history.list, {});
  expect(rows).toHaveLength(100); // list is capped for display
  expect(rows[0].question).toBe("newest");
  const total = await t.run(async (ctx) =>
    (await ctx.db.query("history").collect()).length
  );
  expect(total).toBe(200); // 199 old rows survived plus the new one
  const oldest = await t.run(async (ctx) =>
    ctx.db
      .query("history")
      .withIndex("by_user", (q) => q.eq("userId", "test|user1"))
      .order("asc")
      .first()
  );
  expect(oldest?.question).toBe("old1");
});

test("add below the cap evicts nothing", async () => {
  const t = convexTest(schema, modules);
  const me = t.withIdentity(ME);
  await me.mutation(api.history.add, { question: "a", rawXml: "<a/>" });
  await me.mutation(api.history.add, { question: "b", rawXml: "<a/>" });
  const rows = await me.query(api.history.list, {});
  expect(rows.map((r) => r.question)).toEqual(["b", "a"]);
});
