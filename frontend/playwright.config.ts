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
    extraHTTPHeaders,
  },
  ...(!process.env.BASE_URL && {
    webServer: {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      env: {
        VITE_TEST_BYPASS_AUTH: 'true',
      },
    },
  }),
});
