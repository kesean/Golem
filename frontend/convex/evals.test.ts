/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { expect, test } from "vitest";
import { api } from "./_generated/api";
import schema from "./schema";

const modules = import.meta.glob("./**/*.ts");

// ── createEval ────────────────────────────────────────────────────────────────

test("createEval inserts a record and returns its id", async () => {
  const t = convexTest(schema, modules);
  const evalId = await t
    .withIdentity({ tokenIdentifier: "test|user1" })
    .mutation(api.evals.createEval, {
      question: "Why am I getting a 401?",
      response: "<summary>Test</summary>",
      latency_ms: 500,
      input_tokens: 100,
      output_tokens: 200,
    });
  expect(typeof evalId).toBe("string");
  expect(evalId.length).toBeGreaterThan(0);
});

test("createEval throws when unauthenticated", async () => {
  const t = convexTest(schema, modules);
  await expect(
    t.mutation(api.evals.createEval, {
      question: "Why?",
      response: "<summary>Test</summary>",
      latency_ms: 100,
      input_tokens: 10,
      output_tokens: 20,
    })
  ).rejects.toThrow("Unauthenticated");
});

// ── setFeedback ───────────────────────────────────────────────────────────────

test("setFeedback patches feedback to 'up'", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, {
    evalId,
    feedback: "up",
  });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBe("up");
});

test("setFeedback switches feedback from 'up' to 'down'", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "up" });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "down" });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBe("down");
});

test("setFeedback clears feedback when passed undefined", async () => {
  const t = convexTest(schema, modules);
  const identity = { tokenIdentifier: "test|user1" };
  const evalId = await t.withIdentity(identity).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: "up" });
  await t.withIdentity(identity).mutation(api.evals.setFeedback, { evalId, feedback: undefined });
  const record = await t.run(async (ctx) => ctx.db.get(evalId));
  expect(record?.feedback).toBeUndefined();
});

test("setFeedback throws for a record owned by another user", async () => {
  const t = convexTest(schema, modules);
  const id1 = { tokenIdentifier: "test|user1" };
  const id2 = { tokenIdentifier: "test|user2" };
  const evalId = await t.withIdentity(id1).mutation(api.evals.createEval, {
    question: "Why?",
    response: "<summary>Test</summary>",
    latency_ms: 100,
    input_tokens: 10,
    output_tokens: 20,
  });
  await expect(
    t.withIdentity(id2).mutation(api.evals.setFeedback, { evalId, feedback: "up" })
  ).rejects.toThrow("Not found");
});
