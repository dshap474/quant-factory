/**
 * Rendered ML Engine dashboard state and responsive smoke tests.
 *
 * USAGE:
 *   pnpm exec playwright test e2e/ml-engine.spec.ts
 */

// --------------------------------------------------------------------------- #
// Imports and fixtures
// --------------------------------------------------------------------------- #

import { expect, type Page, test } from '@playwright/test';

// Running fixtures need a live heartbeat: the UI treats a run with no update
// for ML_ENGINE_STALE_RUNNING_MS as a zombie, so a pinned timestamp would make
// these tests pass only on the day they were written.
const heartbeat = new Date().toISOString();

const baseRun = {
  schema_version: 1,
  run_id: '20240102T120000Z-running',
  producer: 'generic.training.consumer',
  status: 'running',
  operation: 'fit elastic-net on fold 3',
  stage: 'cross_validation',
  task: 'regression',
  target: 'forward_value',
  feature_count: 128,
  final_refit: true,
  candidate: 'elastic-net',
  candidate_index: 2,
  candidate_count: 3,
  fold_index: 3,
  fold_count: 5,
  completed_fits: 7,
  total_fits: 15,
  started_at: '2024-01-02T12:00:00Z',
  updated_at: heartbeat,
  completed_at: null,
  host: 'training-host-01',
  inference_ready: false,
  error: null,
};

const readyRun = {
  ...baseRun,
  run_id: '20240102T115000Z-completed-inference-ready-with-a-long-identifier',
  producer: 'batch.example',
  status: 'completed',
  operation: 'artifact saved',
  stage: 'artifact_save',
  completed_fits: 15,
  started_at: '2024-01-02T11:50:00Z',
  completed_at: '2024-01-02T11:54:00Z',
  updated_at: '2024-01-02T11:54:00Z',
  inference_ready: true,
};

const oosRun = {
  ...readyRun,
  run_id: '20240102T110000Z-oos-only',
  producer: 'evaluation.consumer',
  operation: 'evaluation complete',
  stage: 'evaluation',
  final_refit: false,
  inference_ready: false,
};

const failedRun = {
  ...baseRun,
  run_id: '20240102T100000Z-failed',
  producer: 'failure.fixture',
  status: 'failed',
  operation: 'fit candidate ridge on fold 1',
  completed_at: '2024-01-02T10:00:09Z',
  error: { type: 'ValueError', message: 'training matrix contains non-finite values' },
};

const oldRunningRun = {
  ...baseRun,
  run_id: '20240101T090000Z-old-running',
  producer: 'older.worker',
  completed_fits: 2,
  updated_at: heartbeat,
};

const allRuns = [baseRun, readyRun, oosRun, failedRun, oldRunningRun];
const screenshotDirectory = process.env.ML_ENGINE_SCREENSHOT_DIR;

async function captureState(page: Page, name: string) {
  if (!screenshotDirectory) return;
  await page.screenshot({ path: `${screenshotDirectory}/${name}.png`, fullPage: false });
}

function detailFor(run: (typeof allRuns)[number]) {
  return {
    run,
    artifact:
      run.run_id === readyRun.run_id
        ? {
            path: `db/ml-engine/${run.run_id}`,
            manifest: { format: 'ml-engine-training-result' },
            config: { final_refit: true },
            schema: { feature_count: 128 },
            metrics: {
              'elastic-net': {
                candidate: 'elastic-net',
                coverage: 1,
                metrics: { rmse: 0.418321 },
                n_folds: 5,
                n_observations: 240,
                n_periods: 48,
              },
            },
            selection: {
              selected_name: 'elastic-net',
              selected_candidates: ['elastic-net'],
              primary_metric: 'rmse',
              direction: 'minimize',
            },
          }
        : null,
  };
}

const producerFamilies = [...new Set(allRuns.map((run) => run.producer.split('/')[0]))].sort();

async function mockMlEngineApi(page: Page) {
  await page.route('**/api/ml-engine/**', async (route) => {
    const { pathname, searchParams } = new URL(route.request().url());
    if (pathname === '/api/ml-engine/producers') {
      await route.fulfill({ json: { producers: producerFamilies, invalid_count: 0 } });
      return;
    }
    if (pathname === '/api/ml-engine/runs') {
      const producer = searchParams.get('producer');
      const status = searchParams.get('status');
      const runs = allRuns.filter(
        (run) =>
          (producer === null || run.producer === producer) &&
          (status === null || run.status === status),
      );
      await route.fulfill({ json: { runs, count: runs.length, invalid_count: 2 } });
      return;
    }
    const runId = decodeURIComponent(pathname.slice('/api/ml-engine/runs/'.length));
    const run = allRuns.find((candidate) => candidate.run_id === runId);
    await route.fulfill(
      run ? { json: detailFor(run) } : { status: 404, json: { detail: 'ML Engine run not found' } },
    );
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

test.describe('ML Engine dashboard', () => {
  test('renders the dense desktop index and every terminal run state', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockMlEngineApi(page);
    await page.goto('/ml-engine');

    await expect(page).toHaveURL(/\/ml-engine$/);
    await expect(page.getByRole('complementary', { name: 'ML Engine navigation' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Collapse ML Engine navigation' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'ML Engine' })).toBeVisible();
    await expect(page.getByText('fit → evaluate → artifact')).toBeVisible();
    await expect(page.getByText('active now')).toBeVisible();
    await expect(page.getByText('malformed omitted')).toBeVisible();
    await expect(page.getByRole('progressbar')).toHaveCount(0);
    await captureState(page, 'ml-engine-desktop-overview');

    await page.getByRole('button', { name: /generic\.training\.consumer/ }).click();
    await expect(page).toHaveURL(new RegExp(`run=${baseRun.run_id}`));
    await expect(page.getByRole('heading', { name: 'ML Engine' })).toHaveCount(0);
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '7');
    await captureState(page, 'ml-engine-desktop-running');

    await page.getByRole('button', { name: /batch\.example/ }).click();
    await expect(page).toHaveURL(new RegExp(`run=${readyRun.run_id}`));
    await expect(page.getByText('Inference-ready artifact')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible();
    await expect(page.getByText('OOS observations')).toBeVisible();
    await expect(page.getByText('240', { exact: true })).toBeVisible();
    await captureState(page, 'ml-engine-desktop-inference-ready');

    await page.getByRole('button', { name: /evaluation\.consumer/ }).click();
    await expect(page.getByText('OOS-only run; no inference artifact')).toBeVisible();
    await captureState(page, 'ml-engine-desktop-oos-only');

    await page.getByRole('button', { name: /failure\.fixture/ }).click();
    await expect(page.getByRole('alert')).toContainText(
      'ValueError: training matrix contains non-finite values',
    );
    await captureState(page, 'ml-engine-desktop-failed');

    await page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'ML Engine' })
      .click();
    await expect(page).toHaveURL(/\/ml-engine$/);
    await expect(page.getByRole('heading', { name: 'ML Engine' })).toBeVisible();
  });

  test('uses the shared collapsible run navigator at narrow width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockMlEngineApi(page);
    await page.goto('/ml-engine');

    const expandNavigator = page.getByRole('button', { name: 'Expand ML Engine navigation' });
    await expect(expandNavigator).toBeVisible();
    await expandNavigator.click();
    // The narrow navigator has no room for the filter's equal segments, so it is a dropdown.
    await expect(page.getByRole('combobox', { name: 'Filter ML Engine runs' })).toBeVisible();
    await expect(page.getByRole('button', { name: /generic\.training\.consumer/ })).toBeVisible();
    await page.getByRole('button', { name: /batch\.example/ }).click();
    await expect(page.getByRole('button', { name: 'Expand ML Engine navigation' })).toBeVisible();
    await expect(page.getByText('Inference-ready artifact')).toBeVisible();
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390);
    await captureState(page, 'ml-engine-narrow-running');
  });

  test('filters through the API so a buried producer stays reachable', async ({ page }) => {
    // The unfiltered page is a bounded window that a run flood has pushed
    // readyRun out of; only the API filter can still reach it.
    await page.route('**/api/ml-engine/**', async (route) => {
      const { pathname, searchParams } = new URL(route.request().url());
      if (pathname === '/api/ml-engine/producers') {
        await route.fulfill({ json: { producers: producerFamilies, invalid_count: 0 } });
        return;
      }
      if (pathname === '/api/ml-engine/runs') {
        const matched = searchParams.get('producer') === readyRun.producer ? [readyRun] : [baseRun];
        await route.fulfill({ json: { runs: matched, count: matched.length, invalid_count: 0 } });
        return;
      }
      const runId = decodeURIComponent(pathname.slice('/api/ml-engine/runs/'.length));
      await route.fulfill({ json: detailFor(runId === readyRun.run_id ? readyRun : baseRun) });
    });
    await page.goto('/ml-engine');
    await expect(page.getByRole('button', { name: /batch\.example/ })).toHaveCount(0);

    await page.getByRole('combobox', { name: 'Filter runs by producer' }).click();
    await page.getByRole('option', { name: readyRun.producer, exact: true }).click();

    await expect(page.getByRole('button', { name: /batch\.example/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: readyRun.run_id })).toHaveCount(0);
    await page.getByRole('button', { name: /batch\.example/ }).click();
    await expect(page.getByRole('heading', { name: readyRun.run_id })).toBeVisible();
  });

  test('preserves a bookmarked run outside the newest inventory window', async ({ page }) => {
    await page.route('**/api/ml-engine/**', async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === '/api/ml-engine/producers') {
        await route.fulfill({ json: { producers: producerFamilies, invalid_count: 0 } });
        return;
      }
      if (pathname === '/api/ml-engine/runs') {
        await route.fulfill({ json: { runs: [baseRun], count: 1, invalid_count: 0 } });
        return;
      }
      await route.fulfill({ json: detailFor(readyRun) });
    });

    await page.goto(`/ml-engine?run=${readyRun.run_id}`);

    await expect(page).toHaveURL(new RegExp(`run=${readyRun.run_id}`));
    await expect(page.getByRole('heading', { name: readyRun.run_id })).toBeVisible();
    await expect(page.getByRole('button', { name: /batch\.example/ })).toHaveAttribute(
      'aria-current',
      'true',
    );
  });

  test('retains stable loading geometry and handles empty and API-error states', async ({
    page,
  }) => {
    let releaseRequest: (() => void) | undefined;
    const requestGate = new Promise<void>((resolve) => {
      releaseRequest = resolve;
    });
    await page.route('**/api/ml-engine/producers', (route) =>
      route.fulfill({ json: { producers: [], invalid_count: 0 } }),
    );
    await page.route('**/api/ml-engine/runs', async (route) => {
      await requestGate;
      await route.fulfill({ json: { runs: [], count: 0, invalid_count: 0 } });
    });
    await page.goto('/ml-engine');
    await expect(page.getByRole('status', { name: 'Loading rows' }).first()).toBeVisible();
    await captureState(page, 'ml-engine-loading');
    releaseRequest?.();
    await expect(page.getByText('no ML Engine runs yet')).toBeVisible();
    await captureState(page, 'ml-engine-empty');

    await page.unroute('**/api/ml-engine/runs');
    await page.route('**/api/ml-engine/runs', (route) =>
      route.fulfill({ status: 500, json: { detail: 'ML Engine run metadata is invalid' } }),
    );
    await page.reload();
    await expect(page.getByText('run index unavailable')).toBeVisible();
    await captureState(page, 'ml-engine-api-error');
  });

  test('shows progress from the next polling snapshot without a restart', async ({ page }) => {
    let detailRequests = 0;
    await page.route('**/api/ml-engine/**', async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === '/api/ml-engine/producers') {
        await route.fulfill({ json: { producers: producerFamilies, invalid_count: 0 } });
        return;
      }
      if (pathname === '/api/ml-engine/runs') {
        await route.fulfill({ json: { runs: [baseRun], count: 1, invalid_count: 0 } });
        return;
      }
      const updatedRun = {
        ...baseRun,
        completed_fits: detailRequests > 0 ? 8 : 7,
        fold_index: detailRequests > 0 ? 4 : 3,
      };
      detailRequests += 1;
      await route.fulfill({ json: { run: updatedRun, artifact: null } });
    });
    await page.goto(`/ml-engine?run=${baseRun.run_id}`);
    await expect(page.getByText('7 / 15').first()).toBeVisible();
    await expect(page.getByText('8 / 15').first()).toBeVisible({ timeout: 4_000 });
  });

  test('disables decorative motion when reduced motion is requested', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await mockMlEngineApi(page);
    await page.goto(`/ml-engine?run=${baseRun.run_id}`);
    await expect(page.locator('.ui-status-dot.is-running').first()).toHaveCSS(
      'animation-name',
      'none',
    );
    await expect(page.locator('.ui-progress-bar-fill')).toHaveCSS('transition-duration', '0s');
  });
});
