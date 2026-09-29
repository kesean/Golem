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

test('reopen tour from last step shows first step', async ({ page }) => {
  await page.goto('/');
  await page.locator('#tour-btn').click();
  const dialog = page.getByTestId('tour-dialog');
  // Navigate to last step
  await dialog.getByRole('button', { name: 'Next' }).click();
  await dialog.getByRole('button', { name: 'Next' }).click();
  await expect(dialog.getByText('History, feedback and live stats')).toBeVisible();
  // Click Done (which closes the tour)
  await dialog.getByRole('button', { name: 'Done' }).click();
  await expect(page.getByTestId('tour-dialog')).toHaveCount(0);
  // Reopen tour via #tour-btn
  await page.locator('#tour-btn').click();
  // Immediately assert first step is visible
  const reopenedDialog = page.getByTestId('tour-dialog');
  await expect(reopenedDialog.getByText('Ask a technical question')).toBeVisible();
  await expect(reopenedDialog.getByText('Step 1 of 3')).toBeVisible();
  // Ensure Step 3 text is not visible
  await expect(reopenedDialog.getByText('Step 3 of 3')).not.toBeVisible();
});

test.describe('first visit', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('tour auto-opens, resets on reopen, and is not shown again once dismissed', async ({ page }) => {
    await page.goto('/');
    const dialog = page.getByTestId('tour-dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('Step 1 of 3')).toBeVisible();
    await dialog.getByRole('button', { name: 'Next' }).click();
    await dialog.getByRole('button', { name: 'Back' }).click();
    // Back unmounts itself on step 1; focus must stay inside the dialog
    await expect(dialog.getByRole('button', { name: 'Next' })).toBeFocused();
    await dialog.getByRole('button', { name: 'Skip' }).click();
    await expect(dialog).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId('tour-dialog')).toHaveCount(0);
  });
});
