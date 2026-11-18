import { mutation, query, internalMutation } from "./_generated/server";

// The counter is one row. Two first-ever writes that both saw an empty table
// could each insert one, so every read and write treats ALL rows (a small
// bounded read) as the counter: the total is their sum, and increment folds
// them into the oldest row. Convex mutations are serializable, so this is a
// defensive reconcile, not a fix for an observed race.
const STATS_ROW_SCAN = 10;

// Public — no auth required. Read by every visitor, including guests, to
// show the global "N questions answered" counter in the header.
export const getGlobalCount = query({
  args: {},
  handler: async (ctx) => {
    const rows = await ctx.db.query("stats").take(STATS_ROW_SCAN);
    return rows.reduce((sum, row) => sum + row.totalQuestions, 0);
  },
});

// Public — no auth required, by design. Called once per successfully
// answered question, for guests and signed-in users alike. Guests have no
// Convex identity (Convex only trusts Clerk), so an auth check here would
// drop guest usage. Accepted risk: anyone can inflate this cosmetic counter.
export const increment = mutation({
  args: {},
  handler: async (ctx) => {
    const rows = await ctx.db.query("stats").take(STATS_ROW_SCAN);
    if (rows.length === 0) {
      await ctx.db.insert("stats", { totalQuestions: 1 });
      return;
    }
    // Query order is ascending creation time, so rows[0] is the oldest row.
    const [canonical, ...duplicates] = rows;
    const total = rows.reduce((sum, row) => sum + row.totalQuestions, 0) + 1;
    await ctx.db.patch(canonical._id, { totalQuestions: total });
    for (const duplicate of duplicates) {
      await ctx.db.delete(duplicate._id);
    }
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
