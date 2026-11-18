import { test, expect } from '@playwright/test';

const MOCK_TEXT = '<summary>Test summary.</summary>';
const MOCK_SSE_BODY =
  `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
  `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 1, output_tokens: 1, latency_ms: 1, chunks: [] })}\n\n`;

// Hold the answer long enough for the thinking indicator to be on screen.
async function openThinkingDots(page: import('@playwright/test').Page) {
  await page.route('**/ask', async route => {
    await new Promise(resolve => setTimeout(resolve, 2500));
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: MOCK_SSE_BODY });
  });
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401?');
  await page.locator('#ask-btn').click();
  const dot = page.locator('.thinking-dot').first();
  await expect(dot).toBeVisible();
  return dot;
}

test.describe('prefers-reduced-motion: reduce', () => {
  test.use({ reducedMotion: 'reduce' });

  test('thinking dots have no running animation', async ({ page }) => {
    const dot = await openThinkingDots(page);
    expect(await dot.evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  });
});

test.describe('prefers-reduced-motion: no-preference (control)', () => {
  test.use({ reducedMotion: 'no-preference' });

  test('thinking dots animate by default, so the reduce test is meaningful', async ({ page }) => {
    const dot = await openThinkingDots(page);
    expect(await dot.evaluate(el => getComputedStyle(el).animationName)).toBe('thinking-bounce');
  });
});
