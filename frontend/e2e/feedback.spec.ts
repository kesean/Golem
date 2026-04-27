import { test, expect } from '@playwright/test';

const MOCK_RESPONSE = {
  response: '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>',
  input_tokens: 50,
  output_tokens: 100,
  latency_ms: 500,
};

test.beforeEach(async ({ page }) => {
  // Mock the /ask endpoint so no real Flask server is needed
  await page.route('**/ask', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_RESPONSE),
    });
  });
});

test('thumb buttons are not visible before any response is received', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#thumb-up-btn')).not.toBeVisible();
  await expect(page.locator('#thumb-down-btn')).not.toBeVisible();
});

test('thumb buttons are enabled after a response renders', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await expect(page.locator('#thumb-up-btn')).not.toBeDisabled();
  await expect(page.locator('#thumb-down-btn')).not.toBeDisabled();
});

test('clicking thumb-up activates it', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);
  await expect(page.locator('#thumb-down-btn')).not.toHaveClass(/active-down/);
});

test('clicking active thumb-up again deactivates it (toggle off)', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);
  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).not.toHaveClass(/active-up/);
});

test('clicking thumb-down after thumb-up switches selection', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();

  await page.locator('#thumb-up-btn').click();
  await expect(page.locator('#thumb-up-btn')).toHaveClass(/active-up/);

  await page.locator('#thumb-down-btn').click();
  await expect(page.locator('#thumb-down-btn')).toHaveClass(/active-down/);
  await expect(page.locator('#thumb-up-btn')).not.toHaveClass(/active-up/);
});

test('thumb buttons reset to disabled after New Conversation', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await page.locator('#thumb-up-btn').click();

  // Click "New conversation" button
  await page.getByRole('button', { name: 'New conversation' }).click();
  await expect(page.locator('#thumb-up-btn')).not.toBeVisible();
});
