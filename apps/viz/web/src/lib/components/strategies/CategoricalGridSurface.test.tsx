// @vitest-environment jsdom
/** Categorical matrix, curve identity and rank view checks. USAGE: pnpm vitest run CategoricalGridSurface.test.tsx. */

// --------------------------------------------------------------------------- #
// Imports and controlled API responses
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CategoricalGridSurface } from './CategoricalGridSurface';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const fixture = vi.hoisted(() => ({
  ids: ['candidate_cost', 'candidate_free', 'control_cost', 'control_free'],
  chart: {
    series: [] as Array<{ metric: string; isBenchmark?: boolean; points: Array<{ y: number }> }>,
  },
  rank: { data: undefined as unknown, error: null as Error | null, enabled: [] as boolean[] },
}));
vi.mock('@quant-factory/qf-ui/charts/renderers', () => ({
  PortfolioDrawdownChart: (props: typeof fixture.chart) => {
    fixture.chart = props;
    return <div data-chart="shared" />;
  },
}));
vi.mock('@tanstack/react-query', () => {
  const grid = {
    error: null,
    data: {
      dimensions: [
        { key: 'arm', label: 'Arm', format: 'text' },
        { key: 'cost', label: 'Cost', format: 'number' },
      ],
      metrics: [
        { key: 'total_return', label: 'Total return', format: 'percent', higher_is_better: true },
      ],
      data: fixture.ids.map((id, index) => ({
        config_id: id,
        arm: index < 2 ? 'candidate' : 'control',
        cost: index % 2 ? 0 : 7,
        total_return: (index + 1) / 100,
      })),
    },
  };
  return {
    useQuery: (options: { queryKey: readonly unknown[]; enabled?: boolean }) => {
      if (!options.queryKey.includes('rank')) return grid;
      fixture.rank.enabled.push(options.enabled === true);
      return options.enabled
        ? { data: fixture.rank.data, error: fixture.rank.error }
        : { data: undefined, error: null };
    },
    useQueries: () =>
      fixture.ids.map((_, index) => ({
        error: null,
        data: {
          data: [{ date: '2026-08-31', selected_portfolio_value: 101 + index }],
          metrics: {
            selected: {
              sortino: 2.5 + index,
              calmar: 1.5,
              martin: 1.75,
              longest_drawdown_days: 42,
              current_drawdown_days: 3,
            },
          },
        },
      })),
  };
});

function rankPayload(memoryVersion = 'v009') {
  const cell = (rank: number, value: number) => ({
    rank,
    count: 5,
    ties: 0,
    position: (rank - 1) / 4,
    value,
  });
  return {
    strategy_type: 'example',
    memory_version: memoryVersion,
    label: 'Against published versions',
    conventions: 'Population SD; 0% Sortino target.',
    metrics: [
      { key: 'total_return', aliases: [], direction: 'higher' },
      { key: 'sortino', aliases: [], direction: 'higher' },
      { key: 'calmar', aliases: [], direction: 'higher' },
      { key: 'martin', aliases: [], direction: 'higher' },
      { key: 'longest_drawdown_days', aliases: [], direction: 'lower' },
      { key: 'current_drawdown_days', aliases: [], direction: 'lower' },
    ],
    window: {
      start_mark: '2026-01-01',
      first_return: '2026-01-02',
      end: '2026-08-31',
      observations: 242,
    },
    unavailable_reason: null,
    peers: [
      {
        memory_version: 'v001',
        display_state: 'candidate',
        source: 'strategy',
        config_id: null,
        values: {},
      },
    ],
    excluded: [
      {
        memory_version: 'v002',
        reason: 'rejected',
        detail: 'Rejected surface: not correctness-valid.',
      },
    ],
    columns: fixture.ids.map((id, index) => ({
      config_id: id,
      values: {},
      ranks: {
        total_return: cell(4 - index, 0.0123 + index),
        sortino: cell(4 - index, 9.876 + index),
        calmar: null,
        martin: cell(1, 1),
        longest_drawdown_days: cell(2, 40),
        current_drawdown_days: cell(2, 3),
      },
    })),
  };
}

let root: Root | undefined;
let host: HTMLDivElement | undefined;
function mount(memoryVersion = 'v009') {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
  act(() =>
    root?.render(<CategoricalGridSurface strategyType="example" memoryVersion={memoryVersion} />),
  );
  return host;
}
function chooseRank(target: HTMLElement) {
  const option = [...target.querySelectorAll('[role="radio"]')].find(
    (item) => item.textContent === 'Rank',
  );
  act(() => (option as HTMLElement).click());
}
function headers(target: HTMLElement) {
  return [...target.querySelectorAll('thead th')].map((cell) => cell.textContent);
}
afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  document.body.innerHTML = '';
  fixture.rank = { data: undefined, error: null, enabled: [] };
});

// --------------------------------------------------------------------------- #
// Rendered comparison identity
// --------------------------------------------------------------------------- #

describe('CategoricalGridSurface', () => {
  it('passes BTC as a benchmark overlay without adding it to the performance matrix', () => {
    const markup = renderToStaticMarkup(
      <CategoricalGridSurface
        strategyType="example"
        memoryVersion="v009"
        benchmarkSeries={{
          metric: 'btc_buy_hold',
          label: 'BTC buy & hold',
          axis: 'left',
          isBenchmark: true,
          points_total: 1,
          points_returned: 1,
          points: [{ x: '2026-08-31T00:00:00', y: 150 }],
        }}
      />,
    );
    expect(fixture.chart.series).toHaveLength(5);
    expect(fixture.chart.series.at(-1)).toMatchObject({
      metric: 'btc_buy_hold',
      isBenchmark: true,
    });
    expect(fixture.chart.series.slice(0, 4).map((series) => series.metric)).toEqual(fixture.ids);
    expect(markup).not.toContain('BTC buy &amp; hold');
  });
  it('renders every configuration as its own curve and matrix column', () => {
    const markup = renderToStaticMarkup(
      <CategoricalGridSurface strategyType="example" memoryVersion="v009" />,
    );
    expect(fixture.chart.series.map((series) => series.metric)).toEqual(fixture.ids);
    expect(fixture.chart.series.map((series) => series.points[0].y)).toEqual([101, 102, 103, 104]);
    expect(markup).toContain('Performance matrix');
    expect(markup).toContain('Sortino ratio');
    expect(markup).toContain('Martin ratio');
    expect(markup).toContain('1.750');
    expect(markup).toContain('Sortino ↓');
    expect(markup.indexOf('control · 0')).toBeLessThan(markup.indexOf('candidate · 7'));
    expect(markup).toContain('2.500');
    expect(markup).toContain('42 d');
    expect(markup).toContain('candidate · 7');
    expect(markup).toContain('control · 0');
    expect(markup).toContain('1.00%');
    expect(markup).toContain('4.00%');
    expect(markup).not.toContain('Static control');
  });

  it('defaults to values and fetches ranks only once Rank is chosen', () => {
    fixture.rank.data = rankPayload();
    const target = mount();
    const valuesHeaders = headers(target);
    expect(target.querySelector('[role="radio"][aria-checked="true"]')?.textContent).toBe('Values');
    expect(target.textContent).toContain('2.500');
    expect(target.textContent).not.toContain('/ 5');
    expect(fixture.rank.enabled.every((enabled) => !enabled)).toBe(true);

    chooseRank(target);

    expect(fixture.rank.enabled.at(-1)).toBe(true);
    expect(headers(target)).toEqual(valuesHeaders); // Same columns, same Sortino order.
    expect(valuesHeaders.indexOf('control · 0')).toBeLessThan(
      valuesHeaders.indexOf('candidate · 7'),
    );
    expect(target.textContent).toContain(
      'Against published versions · 2026-01-01 start to 2026-08-31',
    );
    expect(target.textContent).toContain('2 compared (1 other versions + this one) · 1 excluded');
    const sortino = target.querySelector('[aria-label="Sortino ratio, control · 0: rank 1 / 5"]');
    expect(sortino?.textContent).toBe('1 / 5');
    expect(target.querySelector('[aria-label^="Calmar ratio, control · 0"]')).toBeNull();
    expect(target.textContent).toContain('—');
  });
  it('shows the comparison-window raw value, direction and count in the rank tooltip', () => {
    fixture.rank.data = rankPayload();
    const target = mount();
    chooseRank(target);
    const trigger = target.querySelector<HTMLElement>(
      '[aria-label="Sortino ratio, control · 0: rank 1 / 5"]',
    );
    act(() => trigger?.click());
    const popup = document.body.querySelector('.ui-popover')?.textContent ?? '';
    expect(popup).toContain('Value 2026-01-01 to 2026-08-31');
    expect(popup).toContain('12.876');
    expect(popup).not.toContain('5.500'); // Never the full-history value.
    expect(popup).toMatch(/higher/i);
    expect(popup).toContain('5');
  });
  it('shows localized loading, error and unavailable rank states', () => {
    const target = mount();
    chooseRank(target);
    expect(target.querySelector('[role="status"][aria-label="Loading ranks"]')).not.toBeNull();
    act(() => root?.unmount());
    host?.remove();

    fixture.rank.data = rankPayload('v008'); // A previous version's ranks never render.
    const stale = mount();
    chooseRank(stale);
    expect(stale.textContent).not.toContain('/ 5');
    act(() => root?.unmount());
    host?.remove();

    fixture.rank.data = undefined;
    fixture.rank.error = new Error('rank request failed');
    const failed = mount();
    chooseRank(failed);
    expect(failed.textContent).toContain('rank request failed');
    act(() => root?.unmount());
    host?.remove();

    fixture.rank.error = null;
    fixture.rank.data = {
      ...rankPayload(),
      window: null,
      unavailable_reason: 'The common window has fewer than two daily returns.',
    };
    const unavailable = mount();
    chooseRank(unavailable);
    expect(unavailable.textContent).toContain('Rank unavailable');
    expect(unavailable.textContent).toContain('fewer than two daily returns');
  });
});
