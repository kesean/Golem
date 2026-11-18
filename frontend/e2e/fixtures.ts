import { test as base, expect } from '@playwright/test';

export { expect };
export type { Page } from '@playwright/test';

const BYPASS_HEADER = 'x-vercel-protection-bypass';

// Sends the Vercel deployment-protection bypass token only to BASE_URL's origin.
// Third-party requests (Clerk, Convex, the API) never see the token.
export const test = base.extend({
  context: async ({ context, baseURL }, use) => {
    const token = process.env.VERCEL_BYPASS_TOKEN;
    if (token && baseURL) {
      const origin = new URL(baseURL).origin;
      await context.route(
        (url) => url.origin === origin,
        (route) =>
          route.fallback({
            headers: { ...route.request().headers(), [BYPASS_HEADER]: token },
          }),
      );
    }
    await use(context);
  },
});
