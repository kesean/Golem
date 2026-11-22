/// <reference types="vite/client" />
import { convexTest } from "convex-test";
import { afterEach, beforeEach, expect, test } from "vitest";
import schema from "./schema";
import { api } from "./_generated/api";

const modules = import.meta.glob("./**/*.ts");

beforeEach(() => {
  process.env.STATS_INCREMENT_SECRET = "stats-test-secret";
  process.env.EVAL_INGEST_SECRET = "eval-test-secret";
});

afterEach(() => {
  delete process.env.STATS_INCREMENT_SECRET;
  delete process.env.EVAL_INGEST_SECRET;
});

async function postIncrement(t: ReturnType<typeof convexTest>, authorization?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authorization) headers.Authorization = authorization;
  return t.fetch("/stats/increment", { method: "POST", body: "{}", headers });
}

test("POST /stats/increment without the stats secret is refused and leaves the counter alone", async () => {
  const t = convexTest(schema, modules);
  expect((await postIncrement(t)).status).toBe(401);
  expect((await postIncrement(t, "Bearer wrong")).status).toBe(401);
  expect(await t.query(api.stats.getGlobalCount, {})).toBe(0);
});

test("the eval ingest secret does not open /stats/increment", async () => {
  const t = convexTest(schema, modules);
  expect((await postIncrement(t, "Bearer eval-test-secret")).status).toBe(401);
  expect(await t.query(api.stats.getGlobalCount, {})).toBe(0);
});

test("POST /stats/increment with the stats secret increments the counter", async () => {
  const t = convexTest(schema, modules);
  const response = await postIncrement(t, "Bearer stats-test-secret");
  expect(response.status).toBe(200);
  expect(await t.query(api.stats.getGlobalCount, {})).toBe(1);
});

test("with STATS_INCREMENT_SECRET unset, /stats/increment fails closed", async () => {
  delete process.env.STATS_INCREMENT_SECRET;
  const t = convexTest(schema, modules);
  expect((await postIncrement(t, "Bearer ")).status).toBe(401);
  expect((await postIncrement(t, "Bearer eval-test-secret")).status).toBe(401);
});
