import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from './fixtures';

// This spec runs against a deployed origin (preview in CI, or prod locally). The local
// dev server and `vite preview` do not apply vercel.json, and the dev server's inline
// React refresh script would itself violate the CSP.
test.skip(!process.env.BASE_URL, 'security headers spec needs BASE_URL');

const vercelConfig = JSON.parse(
  readFileSync(fileURLToPath(new URL('../vercel.json', import.meta.url)), 'utf8'),
);
const EXPECTED: Record<string, string> = Object.fromEntries(
  vercelConfig.headers
    .find((h: { source: string }) => h.source === '/(.*)')
    .headers.map((h: { key: string; value: string }) => [h.key.toLowerCase(), h.value]),
);

const BASE_ORIGIN = new URL(process.env.BASE_URL ?? 'http://localhost').origin;
const BYPASS_TOKEN = process.env.VERCEL_BYPASS_TOKEN;

// Clerk keeps polling, so 'networkidle' never fires on a real deployment. Wait for the
// load event and give the app a short, bounded window to finish its startup requests.
async function settle(page: Page) {
  await page.waitForLoadState('load');
  await page.waitForTimeout(2000);
}

type Injection = { injected: boolean };

// Serves document responses with the vercel.json headers. If the deployment already sends
// them (preview), the served values are used unchanged and checked by the tests. If it
// does not (prod, before this change ships), the headers are added here so the policy is
// still exercised against real Clerk and Convex hosts.
async function applySecurityHeaders(page: Page): Promise<Injection> {
  const state: Injection = { injected: false };
  await page.route(
    (url) => url.origin === BASE_ORIGIN,
    async (route) => {
      if (route.request().resourceType() !== 'document') return route.fallback();
      // route.fetch skips context routes, so the bypass header is added here.
      const response = await route.fetch({
        headers: {
          ...route.request().headers(),
          ...(BYPASS_TOKEN ? { 'x-vercel-protection-bypass': BYPASS_TOKEN } : {}),
        },
      });
      const served = response.headers();
      const headers = served['content-security-policy']
        ? served
        : { ...served, ...EXPECTED };
      state.injected = !served['content-security-policy'];
      await route.fulfill({ response, headers });
    },
  );
  return state;
}

// Records CSP violations from the top document and from console "Refused to ..." messages,
// which also cover iframes (Clerk and Turnstile run in iframes).
async function recordViolations(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __cspViolations: string[] };
    w.__cspViolations = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      w.__cspViolations.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  const consoleViolations: string[] = [];
  page.on('console', (msg) => {
    const text = msg.text();
    if (/Content Security Policy|Refused to/.test(text)) consoleViolations.push(text);
  });
  return async () => {
    const topViolations = await page
      .evaluate(() => (window as unknown as { __cspViolations?: string[] }).__cspViolations ?? [])
      .catch(() => []);
    return [...topViolations, ...consoleViolations];
  };
}

test('deployment serves the security headers from vercel.json', async ({ page }) => {
  const state = await applySecurityHeaders(page);
  const response = await page.goto('/');
  expect(response?.status()).toBe(200);
  const headers = response!.headers();
  for (const [name, value] of Object.entries(EXPECTED)) {
    expect(headers[name], name).toBe(value);
  }
  // In CI the preview must send the headers itself, not rely on injection here.
  if (process.env.CI) expect(state.injected, 'preview did not send CSP from vercel.json').toBe(false);
});

test('no CSP violations on load', async ({ page }) => {
  await applySecurityHeaders(page);
  const violations = await recordViolations(page);
  await page.goto('/');
  await settle(page);
  expect(await violations()).toEqual([]);
});

test('no CSP violations after an ask (mocked)', async ({ page }) => {
  await applySecurityHeaders(page);
  const violations = await recordViolations(page);
  const MOCK_TEXT =
    '<product_tag>Authentication</product_tag><summary>Test summary.</summary><root_cause>Test root cause.</root_cause><debug_steps>Step 1: Check your logs.</debug_steps><docs></docs>';
  const MOCK_SSE_BODY =
    `data: ${JSON.stringify({ type: 'delta', text: MOCK_TEXT })}\n\n` +
    `data: ${JSON.stringify({ type: 'done', response: MOCK_TEXT, input_tokens: 50, output_tokens: 100, latency_ms: 500, chunks: [] })}\n\n`;
  await page.route('**/ask', (route) =>
    route.fulfill({ status: 200, contentType: 'text/event-stream', body: MOCK_SSE_BODY }),
  );
  await page.goto('/');
  await page.locator('#question').fill('Why am I getting a 401 error?');
  await page.locator('#ask-btn').click();
  await expect(page.locator('#response-area')).toBeVisible();
  await settle(page);
  expect(await violations()).toEqual([]);
});

test('no CSP violations on the evals page', async ({ page }) => {
  await applySecurityHeaders(page);
  const violations = await recordViolations(page);
  await page.goto('/evals');
  await settle(page);
  expect(await violations()).toEqual([]);
});

test('no CSP violations with the theme script (dark and light stored)', async ({ page }) => {
  await applySecurityHeaders(page);
  const violations = await recordViolations(page);
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  await page.evaluate(() => localStorage.setItem('theme', 'light'));
  await page.goto('/');
  await settle(page);
  expect(await violations()).toEqual([]);
});

test('opening the Clerk sign-in modal produces no CSP violations', async ({ page }) => {
  await applySecurityHeaders(page);
  const violations = await recordViolations(page);
  await page.goto('/');
  await settle(page);
  // Clerk exposes window.Clerk once clerk-js has loaded from its frontend API host.
  const opened = await page.evaluate(async () => {
    const clerk = (window as unknown as { Clerk?: { loaded?: boolean; openSignIn?: (o: object) => void; closeSignIn?: () => void } }).Clerk;
    if (!clerk?.loaded || !clerk.openSignIn) return false;
    clerk.openSignIn({});
    return true;
  });
  await page.waitForTimeout(3000);
  expect(await violations()).toEqual([]);
  expect(opened, 'Clerk did not load on the deployment').toBe(true);
});
