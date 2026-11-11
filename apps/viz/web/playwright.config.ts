/**
 * Playwright smoke E2E for the React viz SPA.
 *
 * USAGE:
 *   pnpm run test:e2e
 *
 * Starts Vite preview of the production build on 4174. Live DB API optional —
 * route shells must still render without backend data.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { defineConfig, devices } from '@playwright/test';

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

export default defineConfig({
  testDir: '..',
  testMatch: ['web/e2e/**/*.spec.ts', 'extensions/**/*.spec.ts'],
  testIgnore: ['web/e2e/integration/**', 'extensions/_archive/**'],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // gate:full builds first and sets PLAYWRIGHT_SKIP_BUILD=1 to avoid double-build.
    command: process.env.PLAYWRIGHT_SKIP_BUILD
      ? 'pnpm exec vite preview --host 127.0.0.1 --port 4174 --strictPort'
      : 'pnpm run build && pnpm exec vite preview --host 127.0.0.1 --port 4174 --strictPort',
    url: 'http://127.0.0.1:4174',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
