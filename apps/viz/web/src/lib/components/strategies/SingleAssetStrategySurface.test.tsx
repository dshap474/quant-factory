/** Single-asset view rendering and query-transition tests. USAGE: pnpm vitest run SingleAssetStrategySurface.test.tsx. */
/** @vitest-environment jsdom */

// --------------------------------------------------------------------------- #
// Imports and mocks
// --------------------------------------------------------------------------- #

import type { LineChartProps } from '@quant-factory/qf-ui/charts/renderers';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { SingleAssetView } from '@/lib/api/strategies';
import { SingleAssetStrategySurface } from './SingleAssetStrategySurface';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ get: vi.fn() }));
const chart = vi.hoisted(() => ({ panes: {} as Record<string, LineChartProps> }));

vi.mock('@/lib/api/strategies', async (original) => ({
  ...(await original<object>()),
  getVersionSingleAsset: api.get,
}));
vi.mock('@quant-factory/qf-ui/charts/renderers', async (original) => ({
  ...(await original<object>()),
  MultiSeriesTimeChart: () => <div data-testid="single-asset-chart" />,
  LineChart: (props: LineChartProps) => {
    chart.panes[props.ariaLabel ?? ''] = props;
    return <div data-testid="single-asset-chart" />;
  },
}));

// --------------------------------------------------------------------------- #
// Fixture and harness
// --------------------------------------------------------------------------- #

const available: SingleAssetView = {
  available: true,
  reason: null,
  strategy_type: 'example',
  memory_version: 'v001',
  run_id: '20260910T000000Z-run',
  experiment: 'experiment',
  title: 'Example',
  artifact_contract: 'ordinary_ledger_v1',
  asset: 'BTC',
  assets: ['BTC', 'CFX'],
  cost_bps: 5,
  rebalance_every_bars: 7,
  points_total: 2,
  points_returned: 2,
  downsampled: false,
  first_observed_at: '2023-12-15T00:00:00+00:00',
  last_observed_at: '2023-12-16T00:00:00+00:00',
  ever_held: true,
  peak_abs_weight_percent: 1.25,
  ending_contribution_pp: -0.125,
  methodology: 'Saved ledger method.',
  data: [
    {
      timestamp: '2023-12-15T00:00:00Z',
      price: 100,
      weight_percent: 0,
      cumulative_contribution_pp: 0,
    },
    {
      timestamp: '2023-12-16T00:00:00Z',
      price: null,
      weight_percent: 1.25,
      cumulative_contribution_pp: -0.125,
    },
  ],
};

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;

async function render(asset = 'BTC', configId: string | null = null) {
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <SingleAssetStrategySurface
          strategyType="example"
          memoryVersion="v001"
          selectedRunId="20260910T000000Z-run"
          assets={[asset]}
          configId={configId}
          onConfigChange={() => undefined}
          onAssetsChange={() => undefined}
        />
      </QueryClientProvider>,
    );
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({
    matches: false,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  api.get.mockReset();
  chart.panes = {};
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  client.clear();
  container.remove();
  vi.unstubAllGlobals();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

it('places price and contribution above weight while retaining price gaps and units', async () => {
  api.get.mockResolvedValue(available);
  await render();
  const top = chart.panes['Asset price and cumulative contribution'];
  const bottom = chart.panes['Asset portfolio weight'];
  expect(top?.series.map((series) => [series.axis, series.label])).toEqual([
    [undefined, 'Price (quote currency)'],
    ['primary', 'Cumulative contribution (pp)'],
  ]);
  expect(top?.series[0]?.isBenchmark).toBe(true);
  expect(top?.series[0]?.points[1]?.value).toBeNull();
  expect(top?.series[1]?.points[1]?.value).toBe(-0.125);
  expect(bottom?.series.map((series) => series.label)).toEqual(['Weight (%)']);
  expect(bottom?.series[0]?.points[1]?.value).toBe(1.25);
  expect(container.textContent).toContain('Saved ledger method.');
  expect(container.textContent).not.toContain('ordinary_ledger_v1');
});

it('replaces old curves with chart geometry while another asset loads', async () => {
  api.get.mockResolvedValueOnce(available);
  await render('BTC');
  expect(container.querySelector('[data-testid="single-asset-chart"]')).not.toBeNull();

  api.get.mockReturnValueOnce(new Promise(() => undefined));
  await render('CFX');

  expect(container.querySelector('[data-testid="single-asset-chart"]')).toBeNull();
  expect(container.querySelector('[aria-label="Loading content"]')).not.toBeNull();
});

it('shows an honest unsupported state', async () => {
  api.get.mockResolvedValue({
    available: false,
    reason: 'No supported saved ordinary ledger.',
    strategy_type: 'example',
    memory_version: 'v001',
    run_id: 'run-1',
    asset: null,
    assets: [],
    data: [],
  });
  await render();

  expect(container.textContent).toContain('No supported saved ordinary ledger.');
});

it('keeps a chart frame and retry action when ledger evidence fails validation', async () => {
  api.get.mockRejectedValue(new Error('Selected-run ledger returns do not reconcile'));
  await render();

  expect(container.querySelector('.chart-container-shell')).not.toBeNull();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('do not reconcile');
  const retry = [...container.querySelectorAll('button')].find(
    (button) => button.textContent === 'Retry',
  );
  expect(retry).toBeDefined();
});

it('refuses to paint a response from a different selected run', async () => {
  api.get.mockResolvedValue({ ...available, run_id: 'another-run' });
  await render();

  expect(container.querySelector('[data-testid="single-asset-chart"]')).toBeNull();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    'selected result changed',
  );
});

it('selects the requested attributed account and rejects a mismatched response', async () => {
  api.get.mockResolvedValue({
    ...available,
    artifact_contract: 'asset_attribution_v1',
    config_id: 'scale_1x',
    configurations: [
      { id: 'scale_1x', label: 'Scale 1x' },
      { id: 'scale_2x', label: 'Scale 2x' },
    ],
    rebalance_every_bars: null,
  });
  await render('BTC', 'scale_1x');
  expect(api.get).toHaveBeenCalledWith(
    'example',
    'v001',
    'BTC',
    expect.any(AbortSignal),
    'scale_1x',
  );
  expect(container.querySelector('[aria-label="Configuration"]')?.textContent).toContain(
    'Scale 1x',
  );
  expect(container.textContent).toContain('actual daily holdings');
  await render('BTC', 'scale_2x');
  expect(container.querySelector('[data-testid="single-asset-chart"]')).toBeNull();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    'selected result changed',
  );
});
