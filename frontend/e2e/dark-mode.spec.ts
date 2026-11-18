import { test, expect } from '@playwright/test';

// WCAG 2.x relative luminance and contrast ratio for rgb()/rgba() strings.
function luminance(css: string): number {
  const [r, g, b] = (css.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number).map(c => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test.describe('dark mode with no stored theme', () => {
  test.use({ colorScheme: 'dark', viewport: { width: 360, height: 740 } });

  test('the dark class is applied before the document finishes parsing', async ({ page }) => {
    // The inline script in index.html runs during parsing, so the class must
    // already be present when DOMContentLoaded fires, before React mounts.
    await page.addInitScript(() => {
      document.addEventListener('DOMContentLoaded', () => {
        (window as unknown as { __darkAtDCL: boolean }).__darkAtDCL =
          document.documentElement.classList.contains('dark');
      });
    });
    await page.goto('/');
    await expect(page.locator('#question')).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __darkAtDCL: boolean }).__darkAtDCL)).toBe(true);
    await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  });

  test('question textarea and suggestion chips meet contrast thresholds', async ({ page }, testInfo) => {
    await page.goto('/');
    await expect(page.locator('#question')).toBeVisible();
    await expect(page.locator('.suggested-chip').first()).toBeVisible();

    const styles = async (selector: string) =>
      page.locator(selector).first().evaluate(el => {
        const cs = getComputedStyle(el);
        return { color: cs.color, background: cs.backgroundColor, border: cs.borderTopColor };
      });
    const pageBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

    for (const selector of ['#question', '.suggested-chip']) {
      const s = await styles(selector);
      // Text needs 4.5:1 against its own background (WCAG 1.4.3)
      expect(contrast(s.color, s.background), `${selector} text`).toBeGreaterThanOrEqual(4.5);
      // Control borders need 3:1 against the surrounding page (WCAG 1.4.11)
      expect(contrast(s.border, pageBg), `${selector} border`).toBeGreaterThanOrEqual(3);
    }

    await page.screenshot({ path: testInfo.outputPath('360-dark.png'), fullPage: true });
  });

  test('error state renders in dark mode at 360px', async ({ page }, testInfo) => {
    await page.route('**/ask', async (route) => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' });
    });
    await page.goto('/');
    await page.locator('#question').fill('Why am I getting a 401 error?');
    await page.locator('#ask-btn').click();
    await expect(page.getByRole('alert')).toContainText("Couldn't get an answer");
    await page.screenshot({ path: testInfo.outputPath('360-error-dark.png'), fullPage: true });
  });
});
