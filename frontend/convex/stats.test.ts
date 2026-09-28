/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api, internal } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

test("getGlobalCount returns 0 when no stats row exists", async () => {
  const t = convexTest(schema, modules);
  const count = await t.query(api.stats.getGlobalCount, {});
  expect(count).toBe(0);
});

test("increment creates the row with totalQuestions 1 on first call", async () => {
  const t = convexTest(schema, modules);
  await t.mutation(api.stats.increment, {});
  const count = await t.query(api.stats.getGlobalCount, {});
  expect(count).toBe(1);
});

test("increment patches an existing row by 1 each call", async () => {
  const t = convexTest(schema, modules);
  await t.mutation(api.stats.increment, {});
  await t.mutation(api.stats.increment, {});
  await t.mutation(api.stats.increment, {});
  const count = await t.query(api.stats.getGlobalCount, {});
  expect(count).toBe(3);
});

test("increment and getGlobalCount both work with no identity (guest)", async () => {
  const t = convexTest(schema, modules);
  // Deliberately no .withIdentity(...) anywhere in this test — guests must
  // be able to call both functions.
  await t.mutation(api.stats.increment, {});
  await t.mutation(api.stats.increment, {});
  const count = await t.query(api.stats.getGlobalCount, {});
  expect(count).toBe(2);
});

test("seedFromExisting sets totalQuestions to the current evals count", async () => {
  const t = convexTest(schema, modules);
  await t.run(async (ctx) => {
    for (let i = 0; i < 4; i++) {
      await ctx.db.insert("evals", {
        userId: "test|user1",
        question: `Q${i}`,
        response: "<summary>ok</summary>",
        latency_ms: 100,
        input_tokens: 10,
        output_tokens: 20,
      });
    }
  });
  await t.mutation(internal.stats.seedFromExisting, {});
  const count = await t.query(api.stats.getGlobalCount, {});
  expect(count).toBe(4);
});

test("seedFromExisting throws if a stats row already exists", async () => {
  const t = convexTest(schema, modules);
  await t.mutation(api.stats.increment, {});
  await expect(
    t.mutation(internal.stats.seedFromExisting, {})
  ).rejects.toThrow("stats already seeded");
});
