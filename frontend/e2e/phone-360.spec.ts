import { test, expect } from '@playwright/test';

// Phone-width touch checks at 360x740 (a common Android width).
test.use({ viewport: { width: 360, height: 740 }, hasTouch: true });

for (const signedIn of [false, true]) {
  const name = signedIn ? 'signed-in' : 'guest';
  test(`360px ${name} header: no horizontal overflow, primary buttons 44px tall`, async ({ page }, testInfo) => {
    // The signed-in chrome (Sign out) needs the bypass build's identity seam
    test.skip(signedIn && !!process.env.BASE_URL, 'needs the test-bypass build');
    if (signedIn) {
      await page.addInitScript(() => {
        (window as unknown as { __GOLEM_E2E_SIGNED_IN__: boolean }).__GOLEM_E2E_SIGNED_IN__ = true;
      });
    }
    await page.goto('/');
    await expect(page.locator('#tour-btn')).toBeVisible();
    await expect(page.locator('#question')).toBeVisible();
    if (signedIn) await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();

    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(fits, 'document scrollWidth must not exceed the viewport').toBe(true);

    const buttons = page.locator('header button, #ask-btn');
    const count = await buttons.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const box = await buttons.nth(i).boundingBox();
      const label = await buttons.nth(i).evaluate(el => el.getAttribute('aria-label') || el.textContent?.trim() || el.id);
      expect(box, label).not.toBeNull();
      expect(box!.height, label).toBeGreaterThanOrEqual(44);
    }

    await page.screenshot({ path: testInfo.outputPath(`360-${name}.png`), fullPage: true });
  });
}
