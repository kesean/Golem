import { defineConfig } from '@playwright/test';

const baseURL = process.env.BASE_URL || 'http://localhost:5173';

const extraHTTPHeaders: Record<string, string> = {};
if (process.env.VERCEL_BYPASS_TOKEN) {
  extraHTTPHeaders['x-vercel-protection-bypass'] = process.env.VERCEL_BYPASS_TOKEN;
}

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL,
    // Mark the tour seen by default so it doesn't cover the page in other specs
    storageState: { cookies: [], origins: [{ origin: new URL(baseURL).origin, localStorage: [{ name: 'golem-tour-seen', value: '1' }] }] },
    extraHTTPHeaders,
  },
  ...(!process.env.BASE_URL && {
    webServer: {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      env: {
        VITE_TEST_BYPASS_AUTH: 'true',
        // main.tsx constructs a Convex client at import time; any URL works since /ask is mocked
        VITE_CONVEX_URL: process.env.VITE_CONVEX_URL ?? 'https://placeholder.convex.cloud',
      },
    },
  }),
});
