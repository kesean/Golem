import { test, expect, Page } from '@playwright/test';
import { AxeBuilder, Result } from '@axe-core/playwright';

const MOCK_TEXT =
  '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>';

// SSE body matching the shape /ask streams: one delta event with the full
// text, then a done event with usage metrics.
const MOCK_SSE_BODY =
  `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
  `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 50, output_tokens: 100, latency_ms: 500, chunks: [] })}\n\n`;

test.beforeEach(async ({ page }) => {
  // Mock the /ask endpoint so no real Flask server is needed
  await page.route('**/ask', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: MOCK_SSE_BODY,
    });
  });
});

/**
 * Helper function to scan a page with axe and assert no violations.
 * Ensures the page has real content before scanning (unless disabled).
 */
async function scan(
  page: Page,
  label: string,
  options?: { requireContent?: boolean }
) {
  const { requireContent = true } = options || {};

  // Assert the page has real content (unless disabled for dialogs)
  if (requireContent) {
    await expect(page.locator('#question')).toBeVisible();
    await expect(page.locator('h1')).toBeVisible();
  }

  // Wait for animations and transitions to finish before scanning
  // Let theme/dialog transitions settle so axe doesn't sample mid-flight colors.
  // Infinite animations (e.g. the loading dots) never finish, so skip them.
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter(a => a.effect?.getComputedTiming().endTime !== Infinity)
        .map(a => a.finished),
    ),
  );

  // Run axe-core
  const results = await new AxeBuilder({ page })
    .withTags([
      'wcag2a',
      'wcag2aa',
      'wcag21a',
      'wcag21aa',
      'wcag22aa',
      'best-practice',
    ])
    .analyze();

  // Format violations for clear error reporting
  const violations = results.violations.map((v: Result) => {
    const nodeDetails = v.nodes
      .slice(0, 3)
      .map((n) => `${n.target.join(' ')} - ${n.failureSummary}`)
      .join('; ');
    return `${v.id} (${v.impact}): ${nodeDetails}`;
  });

  expect(violations, label).toEqual([]);
}

// Scan matrix: every state below is scanned in each of its viewports x both
// themes. Each state's setup must assert real content is on screen before the
// scan runs, so a blank or wrong page can't pass axe vacuously.
const VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 375, height: 812 },
} as const;

const THEMES = ['light', 'dark'] as const;

// Seeded into the palette via the test-bypass seam in src/hooks/useHistory.ts
const SEEDED_HISTORY = [
  { _id: 'e2e-1', question: 'Why am I getting a 401 error?', rawXml: MOCK_TEXT, _creationTime: 1 },
  { _id: 'e2e-2', question: 'How do I rotate an API key?', rawXml: MOCK_TEXT, _creationTime: 2 },
];

async function openHistoryPalette(page: Page) {
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Assert it's specifically the history palette by checking for cmdk-input
  await expect(dialog.locator('[cmdk-input]')).toBeVisible();
  return dialog;
}

type ScanState = {
  name: string;
  viewports: (keyof typeof VIEWPORTS)[];
  // false for dialogs, which cover #question and the h1
  requireContent: boolean;
  // Seed SEEDED_HISTORY before the page loads
  seedHistory?: boolean;
  setup: (page: Page) => Promise<void>;
};

const STATES: ScanState[] = [
  {
    name: 'empty state',
    viewports: ['desktop', 'mobile'],
    requireContent: true,
    setup: async () => {},
  },
  {
    name: 'answered state',
    viewports: ['desktop', 'mobile'],
    requireContent: true,
    setup: async (page) => {
      await page.locator('#question').fill('Why am I getting a 401 error?');
      await page.locator('#ask-btn').click();
      await expect(page.locator('#response-area')).toBeVisible();
      await expect(page.getByText('Test summary.')).toBeVisible();
      await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
    },
  },
  {
    name: 'tour dialog open',
    viewports: ['desktop'],
    requireContent: false,
    setup: async (page) => {
      await page.locator('#tour-btn').click();
      await expect(page.getByTestId('tour-dialog')).toBeVisible();
    },
  },
  {
    name: 'history palette open',
    viewports: ['desktop'],
    requireContent: false,
    setup: async (page) => {
      const dialog = await openHistoryPalette(page);
      await expect(dialog.getByText('No history yet.')).toBeVisible();
    },
  },
  {
    name: 'history palette with entries',
    viewports: ['desktop'],
    requireContent: false,
    seedHistory: true,
    setup: async (page) => {
      const dialog = await openHistoryPalette(page);
      await expect(dialog.getByRole('option')).toHaveCount(SEEDED_HISTORY.length);
      await expect(dialog.getByRole('option').first()).toHaveText(SEEDED_HISTORY[0].question);
    },
  },
  {
    name: 'history palette no-match search',
    viewports: ['desktop'],
    requireContent: false,
    seedHistory: true,
    setup: async (page) => {
      const dialog = await openHistoryPalette(page);
      await expect(dialog.getByRole('option')).toHaveCount(SEEDED_HISTORY.length);
      await dialog.locator('[cmdk-input]').fill('zzz no such question');
      await expect(dialog.getByRole('option')).toHaveCount(0);
      await expect(dialog.getByText('No matching questions.')).toBeVisible();
    },
  },
];

for (const state of STATES) {
  for (const viewportName of state.viewports) {
    const viewport = VIEWPORTS[viewportName];
    for (const theme of THEMES) {
      const title = `${state.name}: ${viewport.width}x${viewport.height} ${theme} theme`;
      test(title, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript((t) => localStorage.setItem('theme', t), theme);
        if (state.seedHistory) {
          await page.addInitScript((entries) => {
            (window as { __GOLEM_E2E_HISTORY__?: unknown }).__GOLEM_E2E_HISTORY__ = entries;
          }, SEEDED_HISTORY);
        }
        await page.goto('/');
        await state.setup(page);
        if (theme === 'dark') {
          await expect(page.locator('html')).toHaveClass(/\bdark\b/);
        } else {
          await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
        }
        await scan(page, title, { requireContent: state.requireContent });
      });
    }
  }
}

// 320px viewport test
test('320px viewport: no horizontal scroll, axe clean', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto('/');
  // Wait for #question to be visible
  await expect(page.locator('#question')).toBeVisible();
  // Assert no horizontal scrollbar
  const scrollWidth = await page.evaluate(
    () => document.documentElement.scrollWidth
  );
  const clientWidth = await page.evaluate(
    () => document.documentElement.clientWidth
  );
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  await scan(page, '320px viewport');
});

// Focus ring test
test('focus ring on question input', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/');
  // Focus the question input via keyboard
  let focused = false;
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press('Tab');
    const activeElement = await page.evaluate(
      () => document.activeElement?.id
    );
    if (activeElement === 'question') {
      focused = true;
      break;
    }
  }
  expect(focused).toBe(true);
  // Assert focus ring styling using toHaveCSS
  await expect(page.locator('#question')).toHaveCSS('outline-style', 'solid');
  await expect(page.locator('#question')).toHaveCSS('outline-width', '2px');
});

// Live region test
test('live region announces answer ready', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  // Check that the live region contains the status message
  await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
});
