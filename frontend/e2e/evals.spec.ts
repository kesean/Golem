import { test, expect, Page } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

const rules = { completed: true, format: true, productTag: true, citations: true, retrieval: true };
const T0 = Date.UTC(2026, 3, 5);
const WEEK = 7 * 24 * 3600 * 1000;

const mkRun = (i: number) => {
  const meanScore = 3.6 + (i % 5) * 0.15;
  return {
    _id: `run${i}`, _creationTime: T0 + i * WEEK, label: 'scheduled', gitSha: `a1b2c3${i}d4e5f6`, gitRef: 'main',
    appModel: 'm', judgeModel: 'j', casesVersion: 1, startedAt: T0 + i * WEEK, finishedAt: T0 + i * WEEK + 1000,
    status: 'completed',
    summary: {
      caseCount: 3, gradedCount: 3, errorCount: 0, meanGroundedness: meanScore, meanCoverage: meanScore, meanScore,
      rulePassRate: { completed: 1, format: 1, productTag: 0.9 + (i % 3) * 0.03, citations: 0.8 + (i % 4) * 0.05, retrieval: 0.85 },
      p50LatencyMs: 1, p95LatencyMs: 2, totalInputTokens: 1, totalOutputTokens: 1,
    },
    regressions: i === 11 ? [{ kind: 'caseScoreDrop', caseId: 'clerk-401', baseline: 4.5, current: 3.5 }] : [],
  };
};
const runsAsc = Array.from({ length: 12 }, (_, i) => mkRun(i));
const runs = [...runsAsc].reverse();

const mkResult = (runId: string, caseId: string, g: number, c: number, over: object = {}) => ({
  _id: `${runId}-${caseId}`, runId, caseId, question: `Question for ${caseId}?`,
  response: `<summary>Answer text for ${caseId}.</summary>`, retrievedUrls: [], rules,
  judge: { groundedness: g, coverage: c, keyPointsMissed: ['Rotate the key'], reason: `Grader reason for ${caseId}.` },
  latencyMs: 1, inputTokens: 1, outputTokens: 1, ...over,
});

const details: Record<string, unknown> = {};
for (const r of runs) {
  const i = Number(r._id.slice(3));
  details[r._id] = {
    run: r,
    results: [
      mkResult(r._id, 'clerk-401', 3, 4, { rules: { ...rules, citations: false } }),
      mkResult(r._id, 'cors-preflight', 5, 4),
      mkResult(r._id, 'off-topic-1', 4, 4, { judge: undefined, judgeError: 'timeout' }),
    ],
    previous: i > 0
      ? { run: runsAsc[i - 1], results: [mkResult(runsAsc[i - 1]._id, 'clerk-401', 4, 5), mkResult(runsAsc[i - 1]._id, 'cors-preflight', 5, 4)] }
      : null,
  };
}

async function open(page: Page, theme: 'light' | 'dark', seeded = true) {
  await page.addInitScript(([t, seed]) => {
    localStorage.setItem('theme', t as string);
    if (seed) (window as unknown as { __GOLEM_E2E_EVALS__: unknown }).__GOLEM_E2E_EVALS__ = seed;
  }, [theme, seeded ? { runs, details } : null] as const);
  await page.goto('/evals');
}

test.beforeEach(() => {
  test.skip(!!process.env.BASE_URL, 'needs the test-bypass build');
});

test('loads seeded data and expands a case', async ({ page }) => {
  await open(page, 'light');
  await expect(page.getByRole('heading', { name: 'Evals' })).toBeVisible();
  await expect(page.getByRole('img', { name: /Mean judge score: latest .* trending/ })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Eval runs' }).getByRole('row')).toHaveCount(13);
  const btn = page.getByRole('button', { name: /clerk-401/ });
  await btn.focus();
  await page.keyboard.press('Enter');
  await expect(btn).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByText('Grader reason for clerk-401.')).toBeVisible();
  await expect(page.getByText('citations: pass → fail')).toBeVisible();
  await expect(page.getByText('▼ −1.0').first()).toBeVisible();
});

test('empty state', async ({ page }) => {
  await open(page, 'light', false);
  await expect(page.getByText('No eval runs yet.')).toBeVisible();
});

const VIEWPORTS = { desktop: { width: 1280, height: 800 }, mobile: { width: 375, height: 812 } } as const;
for (const [vp, size] of Object.entries(VIEWPORTS)) {
  for (const theme of ['light', 'dark'] as const) {
    test(`axe clean: ${vp} ${theme}`, async ({ page }) => {
      await page.setViewportSize(size);
      await open(page, theme);
      await page.getByRole('button', { name: /clerk-401/ }).click();
      await expect(page.getByText('Grader reason for clerk-401.')).toBeVisible();
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
        .analyze();
      expect(results.violations.map(v => `${v.id}: ${v.nodes[0]?.failureSummary}`)).toEqual([]);
      if (vp === 'desktop' && process.env.EVALS_SCREENSHOT_DIR) {
        await page.screenshot({ path: `${process.env.EVALS_SCREENSHOT_DIR}/t9-evals-${theme}.png`, fullPage: true });
      }
    });
  }
}
