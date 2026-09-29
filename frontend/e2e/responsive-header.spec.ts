import { test, expect } from '@playwright/test';

test('header does not overflow horizontally at 375px', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  await expect(page.locator('#tour-btn')).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  const box = await page.locator('#tour-btn').boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(375);
});
