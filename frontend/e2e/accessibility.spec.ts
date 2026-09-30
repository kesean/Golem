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

// Empty state tests (no question, no response)
test('empty state: 1280x800 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  // Verify theme matches
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'empty state: 1280x800 light');
});

test('empty state: 1280x800 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  // Verify theme matches
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'empty state: 1280x800 dark');
});

test('empty state: 375x812 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  // Verify theme matches
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'empty state: 375x812 light');
});

test('empty state: 375x812 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  // Verify theme matches
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'empty state: 375x812 dark');
});

// Answered state tests (question filled, response received)
test('answered state: 1280x800 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.getByText('Test summary.')).toBeVisible();
  await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'answered state: 1280x800 light');
});

test('answered state: 1280x800 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.getByText('Test summary.')).toBeVisible();
  await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'answered state: 1280x800 dark');
});

test('answered state: 375x812 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.getByText('Test summary.')).toBeVisible();
  await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'answered state: 375x812 light');
});

test('answered state: 375x812 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.getByText('Test summary.')).toBeVisible();
  await expect(page.locator('[role=status]')).toHaveText('Answer ready.');
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'answered state: 375x812 dark');
});

// Tour dialog tests
test('tour dialog open: 1280x800 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  await page.locator('#tour-btn').click();
  await expect(page.getByTestId('tour-dialog')).toBeVisible();
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'tour dialog: 1280x800 light', { requireContent: false });
});

test('tour dialog open: 1280x800 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  await page.locator('#tour-btn').click();
  await expect(page.getByTestId('tour-dialog')).toBeVisible();
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'tour dialog: 1280x800 dark', { requireContent: false });
});

// History palette tests
test('history palette open: 1280x800 light theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'light');
  await page.goto('/');
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Assert it's specifically the history palette by checking for cmdk-input
  await expect(dialog.locator('[cmdk-input]')).toBeVisible();
  const isDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
  expect(isDark).toBe(false);
  await scan(page, 'history palette: 1280x800 light', { requireContent: false });
});

test('history palette open: 1280x800 dark theme', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.addInitScript((t) => localStorage.setItem('theme', t), 'dark');
  await page.goto('/');
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // Assert it's specifically the history palette by checking for cmdk-input
  await expect(dialog.locator('[cmdk-input]')).toBeVisible();
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await scan(page, 'history palette: 1280x800 dark', { requireContent: false });
});

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
