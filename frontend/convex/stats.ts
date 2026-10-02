import { mutation, query, internalMutation } from "./_generated/server";

// Public — no auth required. Read by every visitor, including guests, to
// show the global "N questions answered" counter in the header.
export const getGlobalCount = query({
  args: {},
  handler: async (ctx) => {
    const row = await ctx.db.query("stats").first();
    return row?.totalQuestions ?? 0;
  },
});

// Public — no auth required, by design. Called once per successfully
// answered question, for guests and signed-in users alike. Guests have no
// Convex identity (Convex only trusts Clerk), so an auth check here would
// drop guest usage. Accepted risk: anyone can inflate this cosmetic counter.
export const increment = mutation({
  args: {},
  handler: async (ctx) => {
    const row = await ctx.db.query("stats").first();
    if (!row) {
      await ctx.db.insert("stats", { totalQuestions: 1 });
      return;
    }
    await ctx.db.patch(row._id, { totalQuestions: row.totalQuestions + 1 });
  },
});

// Internal only — not reachable from any client, by design. Run once,
// manually, via `npx convex run stats:seedFromExisting` after this ships,
// so the counter starts from today's real historical total instead of 0.
// Throws if a stats row already exists, so an accidental second run can't
// clobber a counter that's already live and accumulating real increments.
export const seedFromExisting = internalMutation({
  args: {},
  handler: async (ctx) => {
    const existing = await ctx.db.query("stats").first();
    if (existing) {
      throw new Error("stats already seeded — refusing to overwrite");
    }
    const evalCount = (await ctx.db.query("evals").collect()).length;
    await ctx.db.insert("stats", { totalQuestions: evalCount });
  },
});
