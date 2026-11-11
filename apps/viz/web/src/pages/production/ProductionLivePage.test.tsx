/**
 * Production Live tab: empty state on 404, error state otherwise, and fixture renders.
 *
 * USAGE:
 *   pnpm vitest run src/pages/production/ProductionLivePage.test.tsx
 */
/** @vitest-environment jsdom */

// --------------------------------------------------------------------------- #
// Imports and mocks
// --------------------------------------------------------------------------- #

import type { MultiSeriesTimeChartProps } from '@quant-factory/qf-ui/charts/renderers';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api/errors';
import {
  productionOverviewSchema,
  productionSeriesSchema,
  productionStrategySchema,
} from '@/lib/api/production';
import { ViewerRouterProvider } from '@/ui';
import { EMPTY_HINT, EMPTY_TITLE, ProductionLivePage } from './ProductionLivePage';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => ({ responses: {} as Record<string, unknown> }));
const chart = vi.hoisted(() => ({ props: null as MultiSeriesTimeChartProps | null }));

vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<object>()),
  getParsed: vi.fn(
    async (
      path: string,
      schema: { parse: (value: unknown) => unknown },
      init?: { params?: { path?: { family?: string } } },
    ) => {
      const key = path.replace('{family}', init?.params?.path?.family ?? '');
      const response = api.responses[key];
      if (response instanceof Error) throw response;
      if (response === undefined) throw new ApiError('Not in fixture', 404);
      return schema.parse(response);
    },
  ),
}));
vi.mock('@quant-factory/qf-ui/charts/renderers', async (original) => ({
  ...(await original<object>()),
  MultiSeriesTimeChart: (props: MultiSeriesTimeChartProps) => {
    chart.props = props;
    return <div data-testid="production-chart">{props.title}</div>;
  },
}));

// --------------------------------------------------------------------------- #
// Fixtures (shaped exactly like apps/api/src/db_api/routers/production.py)
// --------------------------------------------------------------------------- #

const metrics = {
  total_pnl_usd: 1250.5,
  total_return: 0.0125,
  max_drawdown: -0.031,
  annualized_volatility: 0.18,
  sharpe: 1.42,
  positive_day_rate: 0.56,
  observation_count: 30,
};

const overview = {
  schema_version: 1,
  portfolio_id: 'main',
  generated_at: '2026-10-06T00:05:00Z',
  completeness: 'incomplete',
  equity_usd: 101250.5,
  today_pnl_usd: -84.25,
  inception_pnl_usd: 1250.5,
  missing_families: ['family-b'],
  stale_families: [],
  included_families: ['family-a'],
  metrics,
  members: [
    {
      family: 'family-a',
      included: true,
      state: 'live',
      health: 'healthy',
      stale: false,
      capital_weight: 1,
      equity_usd: 101250.5,
      inception_pnl_usd: 1250.5,
      period_pnl_usd: 310,
      last_observation_at: '2026-10-06T00:00:00Z',
    },
    {
      family: 'family-b',
      included: false,
      state: null,
      health: 'attention',
      stale: true,
      capital_weight: null,
      equity_usd: null,
      inception_pnl_usd: null,
      period_pnl_usd: null,
      last_observation_at: null,
    },
  ],
};

const line = (family: string | null) => ({
  family,
  points: [
    { day: '2026-10-04', value: 0, complete: true },
    { day: '2026-10-05', value: 120.5, complete: true },
    { day: '2026-10-06', value: null, complete: false },
  ],
});

const series = (family: string | null, strategies: string[]) => ({
  range: '30d',
  metric: 'pnl_usd',
  portfolio_id: 'main',
  generated_at: '2026-10-06T00:05:00Z',
  complete: false,
  aggregate: line(family),
  strategies: strategies.map(line),
});

const strategy = {
  schema_version: 1,
  portfolio_id: 'main',
  generated_at: '2026-10-06T00:05:00Z',
  family: 'family-a',
  included: true,
  state: 'live',
  health: 'healthy',
  stale: false,
  max_age_seconds: 93600,
  last_observation_at: '2026-10-06T00:00:00Z',
  today_pnl_usd: -84.25,
  inception_pnl_usd: 1250.5,
  deployment: {
    family: 'family-a',
    memory_version: 'v004',
    preset: 'base',
    venue: 'example-venue',
    instrument: 'BTC-USD',
    account_alias: 'primary',
    host_alias: 'prod-1',
    host_region: 'region-a',
    schedule: 'daily 00:00',
    timezone: 'UTC',
    host_git_sha: 'abc1234',
    deployment_fingerprint: 'a'.repeat(64),
  },
  authority_facts: {
    activation_state: 'enabled',
    activation_expires_at: null,
    armed: true,
    venue_gate: 'open',
    capital_gate: 'open',
    deactivated: false,
    can_trade: true,
    scheduled: true,
    autonomous_live: true,
  },
  health_checks: [
    { name: 'scheduler', state: 'passing', detail: 'timer active' },
    { name: 'reconciliation', state: 'failing', detail: 'position drift 0.01 BTC' },
  ],
  last_run: {
    result: 'success',
    at: '2026-10-06T00:05:00Z',
    mode: 'live',
    journal_at: '2026-10-06T00:05:00Z',
  },
  capital: {
    as_of: '2026-10-06T00:00:00Z',
    equity_usd: 101250.5,
    cash_usd: 50000,
    gross_exposure_usd: 51250.5,
    net_exposure_usd: 51250.5,
    realized_pnl_usd: 900,
    unrealized_pnl_usd: 350.5,
    fees_usd: -12,
    funding_pnl_usd: null,
    capital_weight: 1,
    positions: [
      {
        instrument: 'BTC-USD',
        side: 'LONG',
        quantity: 0.4,
        contracts: null,
        current_price: 128126.25,
        entry_price: 127250,
        market_value_usd: 51250.5,
        unrealized_pnl_usd: 350.5,
        daily_realized_pnl_usd: null,
      },
    ],
  },
  metrics,
};

// --------------------------------------------------------------------------- #
// Harness
// --------------------------------------------------------------------------- #

let container: HTMLDivElement;
let root: Root;

async function render(url = '/production/live') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[url]}>
          <ViewerRouterProvider>
            <ProductionLivePage />
          </ViewerRouterProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  });
  for (let tick = 0; tick < 5; tick += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

beforeEach(() => {
  api.responses = {};
  chart.props = null;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('production schemas', () => {
  it('parse fixtures that mirror the API response models', () => {
    expect(productionOverviewSchema.parse(overview).members).toHaveLength(2);
    expect(productionSeriesSchema.parse(series(null, ['family-a'])).strategies).toHaveLength(1);
    expect(productionStrategySchema.parse(strategy).capital?.positions[0].side).toBe('LONG');
  });
});

describe('ProductionLivePage', () => {
  it('shows the empty state, not an error, before anything is published', async () => {
    api.responses['/api/production/overview'] = new ApiError(
      'Production projection not found',
      404,
    );
    await render();

    expect(container.textContent).toContain(EMPTY_TITLE);
    expect(container.textContent).toContain(EMPTY_HINT);
    expect(container.textContent).not.toContain('Production projection not found');
    const tabs = container.querySelector('nav[aria-label="Production views"]');
    expect([...(tabs?.querySelectorAll('a') ?? [])].map((link) => link.textContent)).toEqual([
      'Live',
    ]);
  });

  it('keeps the normal error state for any other failure', async () => {
    api.responses['/api/production/overview'] = new ApiError(
      'Production projection is invalid',
      500,
    );
    await render();

    expect(container.textContent).toContain('Production projection is invalid');
    expect(container.textContent).not.toContain(EMPTY_TITLE);
  });

  it('renders the portfolio chart, summary and member table from fixture data', async () => {
    api.responses['/api/production/overview'] = overview;
    api.responses['/api/production/series'] = series(null, ['family-a']);
    await render();

    expect(chart.props?.title).toBe('main · P&L');
    expect(chart.props?.valueFormat).toBe('money');
    expect(chart.props?.series.map((item) => item.label)).toEqual(['Portfolio', 'family-a']);
    expect(chart.props?.series[0].points.at(-1)).toEqual({ x: '2026-10-06', y: null });

    const summary = container.querySelector('[aria-label="Portfolio summary"]');
    expect(summary?.textContent).toContain('NAV');
    expect(summary?.textContent).toContain('1 of 2');
    expect(summary?.textContent).toContain('1 missing');
    expect(summary?.textContent).toContain('+1.25%');

    const link = [...container.querySelectorAll('a')].find(
      (anchor) => anchor.textContent === 'family-a',
    );
    expect(link?.getAttribute('href')).toBe('/production/live?family=family-a');
    expect(container.textContent).toContain('attention');
    expect(container.textContent).toContain('incomplete');
  });

  it('renders one family from ?family= with positions, checks and deployment', async () => {
    api.responses['/api/production/overview'] = overview;
    api.responses['/api/production/strategies/family-a'] = strategy;
    api.responses['/api/production/strategies/family-a/series'] = series('family-a', []);
    await render('/production/live?family=family-a&metric=return_pct');

    expect(chart.props?.title).toBe('family-a · Return');
    expect(chart.props?.valueFormat).toBe('percent-delta');
    expect(chart.props?.series.map((item) => item.label)).toEqual(['family-a']);
    expect(container.textContent).toContain('BTC-USD');
    expect(container.textContent).toContain('position drift 0.01 BTC');
    expect(container.textContent).toContain('v004 · base');
  });
});
