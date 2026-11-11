/** Strategy-version view-tab URL behavior. USAGE: pnpm vitest run StrategyVersionPage.test.tsx. */
/** @vitest-environment jsdom */

// --------------------------------------------------------------------------- #
// Imports and mocks
// --------------------------------------------------------------------------- #

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, Suspense } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewerRouterProvider } from '@/ui';
import { StrategyVersionPage } from './StrategyVersionPage';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const version = vi.hoisted(() => ({ state: 'promoted' }));

vi.mock('@/extensions', () => ({
  strategyCompositionPanel: () => undefined,
  strategyCurrentDataReplay: () => null,
  strategyRedirect: () => null,
  opsPanels: () => [],
}));
vi.mock('@/lib/api/strategies', async (original) => ({
  ...(await original<object>()),
  useStrategyVersions: () => ({
    data: [
      {
        memory_version: 'v001',
        source: 'canonical',
        state: version.state,
        display_state: 'promoted',
        selected_run_id: 'run-1',
        has_surface: false,
      },
    ],
    isSuccess: true,
    isLoading: false,
    error: null,
  }),
  getVersionFinal: vi.fn().mockResolvedValue({ data: [], columns: [] }),
  getVersionRuns: vi.fn().mockResolvedValue([]),
  getVersionSurface: vi.fn(),
}));
vi.mock('@/lib/api/strategy-version-records', async (original) => ({
  ...(await original<object>()),
  useStrategyVersionRecords: () => ({
    data: undefined,
    error: null,
    isFetching: false,
    isPlaceholderData: false,
    refetch: vi.fn(),
  }),
}));
vi.mock('@/lib/components/strategies/SingleAssetStrategySurface', () => ({
  SingleAssetStrategySurface: ({ assets }: { assets: readonly string[] }) => (
    <div data-testid="single-asset-surface">{assets.join(',')}</div>
  ),
}));
vi.mock('./InvalidatedStrategyVersion', () => ({
  InvalidatedStrategyVersion: () => <div data-testid="invalidated-surface" />,
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

// --------------------------------------------------------------------------- #
// Harness
// --------------------------------------------------------------------------- #

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

async function render() {
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/strategies/example/v001?view=composition&assets=BTC']}>
          <LocationProbe />
          <ViewerRouterProvider>
            <Suspense fallback={<div>Loading route</div>}>
              <Routes>
                <Route path="/strategies/:type/:memoryVersion" element={<StrategyVersionPage />} />
              </Routes>
            </Suspense>
          </ViewerRouterProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  version.state = 'promoted';
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
});

// --------------------------------------------------------------------------- #
// Test
// --------------------------------------------------------------------------- #

it('deep-links the selected asset and moves between both top views through the URL', async () => {
  await render();

  expect(container.querySelector('[data-testid="single-asset-surface"]')?.textContent).toBe('BTC');
  expect(container.querySelector('[data-testid="location"]')?.textContent).toContain(
    '?view=composition&assets=BTC',
  );

  const overview = [...container.querySelectorAll('button')].find(
    (button) => button.textContent === 'Overview',
  );
  await act(async () => {
    overview?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });

  expect(container.querySelector('[data-testid="location"]')?.textContent).toContain(
    '?view=overview&assets=BTC',
  );
  expect(container.querySelector('[data-testid="single-asset-surface"]')).toBeNull();
});

it('preserves invalidation when a single-asset URL is requested', async () => {
  version.state = 'invalidated';
  await render();

  expect(container.querySelector('[data-testid="invalidated-surface"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="single-asset-surface"]')).toBeNull();
});
