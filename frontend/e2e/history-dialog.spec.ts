import { test, expect } from '@playwright/test';

// The test bypass renders the signed-in layout only, so the guest "History
// unavailable" dialog cannot be reached here. This covers the signed-in history
// palette, which uses the same focus and Escape behaviour.
test.beforeEach(() => {
  test.skip(!!process.env.BASE_URL, 'needs the test-bypass build');
});

test('history palette traps focus, Escape closes it, and focus returns to the question', async ({ page }) => {
  await page.goto('/');
  await page.locator('#question').focus();
  await page.keyboard.press('Control+k');

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[cmdk-input]')).toBeFocused();

  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
    // Poll rather than read once: the dialog moves focus asynchronously
    await expect
      .poll(() => page.evaluate(() => !!document.activeElement?.closest('[role=dialog]')), {
        message: `focus escaped the dialog on Tab ${i + 1}`,
      })
      .toBe(true);
  }

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(page.locator('#question')).toBeFocused();
});
