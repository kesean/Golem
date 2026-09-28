import { test, expect } from '@playwright/test';

test('tour replay button opens the tour and steps through it', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('tour-dialog')).toHaveCount(0)
  await page.locator('#tour-btn').click();
  const dialog = page.getByTestId('tour-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('Ask a technical question')).toBeVisible();
  await dialog.getByRole('button', { name: 'Next' }).click();
  await expect(dialog.getByText('Get a structured answer')).toBeVisible();
  await dialog.getByRole('button', { name: 'Back' }).click();
  await expect(dialog.getByText('Ask a technical question')).toBeVisible();
  await dialog.getByRole('button', { name: 'Next' }).click();
  await dialog.getByRole('button', { name: 'Next' }).click();
  await expect(dialog.getByText('History, feedback and live stats')).toBeVisible();
  await dialog.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByTestId('tour-dialog')).toHaveCount(0);
});

test('skip closes the tour and marks it seen', async ({ page }) => {
  await page.goto('/');
  await page.locator('#tour-btn').click();
  await page.getByTestId('tour-dialog').getByRole('button', { name: 'Skip' }).click();
  await expect(page.getByTestId('tour-dialog')).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem('golem-tour-seen'))).toBe('1');
});
