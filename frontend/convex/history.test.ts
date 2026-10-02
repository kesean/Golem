/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

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
