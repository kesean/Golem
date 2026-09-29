import { test, expect } from '@playwright/test';
import { DEMO_QUESTIONS } from '../src/lib/demoQuestions';

const MOCK_TEXT =
  '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>';
const MOCK_SSE_BODY =
  `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
  `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 50, output_tokens: 100, latency_ms: 500, chunks: [] })}\n\n`;

test.beforeEach(async ({ page }) => {
  await page.route('**/ask', async (route) => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: MOCK_SSE_BODY });
  });
});

test('shows 5 suggested questions on the empty state', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('suggested-question')).toHaveCount(5);
});

test('clicking a suggestion submits it and hides the suggestions', async ({ page }) => {
  await page.goto('/');
  const requestPromise = page.waitForRequest('**/ask');
  await page.getByTestId('suggested-question').first().click();
  const request = await requestPromise;
  const body = await request.postDataJSON();
  expect(body.question).toBe(DEMO_QUESTIONS[0].question);
  await expect(page.getByText('Test summary.')).toBeVisible();
  await expect(page.getByTestId('suggested-question')).toHaveCount(0);
  const questionValue = await page.locator('#question').inputValue();
  expect(questionValue).toBe(DEMO_QUESTIONS[0].question);
});

test('typing in the input hides the suggestions', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('hello');
  await expect(page.getByTestId('suggested-question')).toHaveCount(0);
});

test('focus moves to the question input after picking a suggestion', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('suggested-question').first().click();
  await expect(page.locator('#question')).toBeFocused();
});

test('suggestions stay hidden while loading and after an error', async ({ page }) => {
  await page.unroute('**/ask');
  await page.route('**/ask', async (route) => {
    await new Promise((r) => setTimeout(r, 500));
    await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' });
  });
  await page.goto('/');
  await page.getByTestId('suggested-question').first().click();
  await expect(page.getByTestId('suggested-question')).toHaveCount(0);
  await expect(page.getByRole('alert').or(page.getByText(/error|wrong|failed/i)).first()).toBeVisible();
  await expect(page.getByTestId('suggested-question')).toHaveCount(0);
});
