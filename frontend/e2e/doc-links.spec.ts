import { test, expect } from '@playwright/test';
import { DEMO_QUESTIONS } from '../src/lib/demoQuestions';

const MOCK_TEXT =
  '<product_tag>Authentication</product_tag><summary>Test summary with documentation.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs>MDN - CORS: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS\nClerk session tokens overview</docs>';
const MOCK_SSE_BODY =
  `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
  `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 50, output_tokens: 100, latency_ms: 500, chunks: [] })}\n\n`;

test.beforeEach(async ({ page }) => {
  await page.route('**/ask', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: MOCK_SSE_BODY });
  });
});

test('doc links are split from titles and rendered correctly', async ({ page }) => {
  await page.goto('/');
  const requestPromise = page.waitForRequest('**/ask');
  await page.getByTestId('suggested-question').first().click();
  const request = await requestPromise;
  const body = await request.postDataJSON();
  expect(body.question).toBe(DEMO_QUESTIONS[0].question);
  await expect(page.getByText('Test summary with documentation.')).toBeVisible();

  // Locate the docs row by its 'Docs' label
  const docsSection = page.locator('section.nb-row', { hasText: 'Docs' }).filter({ hasText: 'MDN - CORS' });

  // Assert: a link named 'MDN - CORS' has href exactly 'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS'
  const corsLink = docsSection.locator('a', { hasText: 'MDN - CORS' });
  await expect(corsLink).toHaveCount(1);
  await expect(corsLink).toHaveAttribute('href', 'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS');

  // Assert: the text 'Clerk session tokens overview' is visible and is NOT inside an <a> within the docs section
  const clerkText = docsSection.getByText('Clerk session tokens overview');
  await expect(clerkText).toBeVisible();
  const clerkLink = docsSection.locator('a', { hasText: 'Clerk session tokens overview' });
  await expect(clerkLink).toHaveCount(0);
});

test('debug steps can be ticked off and the "Step N:" prefix is dropped', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('suggested-question').first().click();
  const step = page.locator('.nb-step').first();
  await expect(step).toContainText('Check your logs.');
  await expect(step).not.toContainText('Step 1:');
  await step.locator('input[type=checkbox]').check({ force: true });
  await expect(step).toHaveClass(/nb-step-done/);
});
