import { test, expect } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

const NOT_FOUND = "This shared link doesn't work. The answer may have been deleted.";

// The bypass build points at a placeholder Convex URL, so the lookup never
// settles and the hook's timeout produces the notFound notice. Against a real
// preview, the Convex validator rejects the malformed id and gives the same result.
test('broken share link shows a notice and recovers (light)', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('theme', 'light'));
  await page.goto('/?share=not-a-valid-id');

  await expect(page).not.toHaveURL(/share=/);
  const notice = page.getByText(NOT_FOUND);
  await expect(notice).toBeVisible({ timeout: 12_000 });

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(' ')}`)).toEqual([]);

  await page.getByRole('button', { name: 'Ask your own question' }).click();
  await expect(page.locator('#question')).toBeFocused();
  await expect(notice).toBeHidden();
});

test('broken share link shows a notice and recovers (dark)', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('theme', 'dark'));
  await page.goto('/?share=not-a-valid-id');

  await expect(page).not.toHaveURL(/share=/);
  const notice = page.getByText(NOT_FOUND);
  await expect(notice).toBeVisible({ timeout: 12_000 });

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(' ')}`)).toEqual([]);

  await page.getByRole('button', { name: 'Ask your own question' }).click();
  await expect(page.locator('#question')).toBeFocused();
  await expect(notice).toBeHidden();
});

test.describe('first-time visitor', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('a share link does not open the tour', async ({ page }) => {
    await page.goto('/?share=not-a-valid-id');
    await expect(page.getByText(NOT_FOUND)).toBeVisible({ timeout: 12_000 });
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});
