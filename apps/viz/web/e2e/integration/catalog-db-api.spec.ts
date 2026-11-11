/**
 * Hermetic browser-to-real-DB-API integration smoke.
 *
 * USAGE:
 *   pnpm run test:e2e:integration
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { expect, test } from '@playwright/test';

import { collectRuntimeIssues, expectNoRuntimeIssues } from '../support/runtime-issues';

// --------------------------------------------------------------------------- #
// Integration smoke
// --------------------------------------------------------------------------- #

test('renders a disposable parquet fixture through the real FastAPI catalog seam', async ({
  page,
  request,
}) => {
  const route = '/catalog?layer=derived';
  const runtimeIssues = collectRuntimeIssues(page);

  const health = await request.get('/health');
  expect(health.ok()).toBe(true);
  await expect(health.json()).resolves.toMatchObject({ status: 'healthy', db_exists: true });

  await page.goto(route);
  await page.getByRole('button', { name: 'integration/' }).click();
  await page.getByRole('button', { name: 'release-seam' }).click();

  await expect(page).toHaveURL(/\/catalog\/view\?.*item=dataset%3Aintegration%2Frelease-seam/);
  await expect(page.getByRole('heading', { name: 'Release Seam' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'real-fastapi-fixture' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '73.25' })).toBeVisible();
  await expectNoRuntimeIssues(route, runtimeIssues);
});
