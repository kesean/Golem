import { test, expect } from '@playwright/test';

const MOCK_TEXT =
  '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>';

const MOCK_CHUNKS = [
  { source: 'Clerk', path: 'docs/authentication/sessions.mdx', text: 'Session verification details.' },
];

function sseBody(chunks: typeof MOCK_CHUNKS) {
  return (
    `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
    `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 50, output_tokens: 100, latency_ms: 500, chunks })}\n\n`
  );
}

test('debug panel is hidden when no docs were retrieved', async ({ page }) => {
  await page.route('**/ask', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: sseBody([]) });
  });

  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.locator('#debug-panel')).not.toBeVisible();
});

test('debug panel shows retrieved chunks, collapsed by default', async ({ page }) => {
  await page.route('**/ask', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: sseBody(MOCK_CHUNKS) });
  });

  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();

  await expect(page.locator('#debug-panel-toggle')).toContainText('Retrieved docs (1)');
  await expect(page.getByText('Session verification details.')).not.toBeVisible();

  await page.locator('#debug-panel-toggle').click();
  await expect(page.getByText('Session verification details.')).toBeVisible();
  await expect(page.getByText('docs/authentication/sessions.mdx')).toBeVisible();
});
