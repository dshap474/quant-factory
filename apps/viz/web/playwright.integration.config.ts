/**
 * Hermetic Viz-to-DB-API Playwright configuration.
 *
 * USAGE:
 *   pnpm run test:e2e:integration
 *   PLAYWRIGHT_SKIP_BUILD=1 pnpm run test:e2e:integration
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

// --------------------------------------------------------------------------- #
// Paths and commands
// --------------------------------------------------------------------------- #

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(webRoot, '../../..');
const apiUrl = 'http://127.0.0.1:18114';
const webUrl = 'http://127.0.0.1:4274';
const previewCommand = process.env.PLAYWRIGHT_SKIP_BUILD
  ? 'VIZ_API_URL=http://127.0.0.1:18114 pnpm exec vite preview --host 127.0.0.1 --port 4274 --strictPort'
  : 'pnpm run build && VIZ_API_URL=http://127.0.0.1:18114 pnpm exec vite preview --host 127.0.0.1 --port 4274 --strictPort';

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

export default defineConfig({
  testDir: './e2e/integration',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: webUrl,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command:
        'uv run --package quant-factory-db-api python apps/viz/web/e2e/support/run-db-api-fixture.py --port 18114',
      cwd: repoRoot,
      url: `${apiUrl}/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      // `uv run` handles SIGINT like an interactive shutdown and waits for the
      // Python child to unwind its TemporaryDirectory context.
      gracefulShutdown: { signal: 'SIGINT', timeout: 5_000 },
    },
    {
      command: previewCommand,
      cwd: webRoot,
      url: webUrl,
      reuseExistingServer: false,
      timeout: 180_000,
      gracefulShutdown: { signal: 'SIGTERM', timeout: 5_000 },
    },
  ],
});
