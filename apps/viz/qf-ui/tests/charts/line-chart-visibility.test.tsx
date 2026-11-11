/**
 * Line-chart visibility transition contract tests.
 *
 * USAGE:
 *   pnpm test -- line-chart-visibility.test.tsx
 */

// --------------------------------------------------------------------------- #
// Mocks
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const capturedOptions = vi.hoisted<Array<Record<string, unknown>>>(() => []);
const capturedPatches = vi.hoisted<Array<Array<Record<string, unknown>> | undefined>>(() => []);

vi.mock('../../src/charts/core/QfChart', () => ({
  QfChart: ({
    option,
    seriesPatch,
  }: {
    option: Record<string, unknown>;
    seriesPatch?: Array<Record<string, unknown>>;
  }) => {
    capturedOptions.push(option);
    capturedPatches.push(seriesPatch);
    return <div data-testid="qf-chart" />;
  },
}));

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { LineChart, type QfLineSeries } from '../../src/charts/charts/LineChart';
import { QF_DARK_THEME } from '../../src/charts/theme/defaults';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const series: readonly QfLineSeries[] = [
  {
    key: 'strategy',
    label: 'Strategy',
    points: [
      { date: new Date('2026-01-01T00:00:00Z'), value: 1 },
      { date: new Date('2026-01-02T00:00:00Z'), value: 2 },
    ],
  },
];

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LineChart visibility transitions', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    capturedPatches.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('renders benchmarks grey and dashed on an independent hidden axis', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <LineChart
          series={[
            ...series,
            { points: series[0]?.points ?? [], key: 'control', label: 'Control', color: 'red' },
            {
              points: series[0]?.points ?? [],
              key: 'btc',
              label: 'BTC',
              isBenchmark: true,
              color: 'red',
            },
          ]}
          height={320}
          benchmarkDomain={[1000, 2000]}
        />,
      ),
    );
    const option = capturedOptions.at(-1) as {
      series: Array<{ id: string; yAxisIndex: number; lineStyle: { type: string; color: string } }>;
      yAxis: Array<{ show: boolean; min?: number; max?: number }>;
    };
    expect(option.series.map((item) => item.yAxisIndex)).toEqual([0, 0, 1]);
    expect(option.series.map((item) => item.lineStyle.type)).toEqual(['solid', 'solid', 'dashed']);
    expect(option.series[2]?.lineStyle.color).not.toBe('red');
    expect(option.yAxis[1]).toMatchObject({ show: false, min: 1000, max: 2000 });
    await act(async () => root.unmount());
  });

  it('shares already-comparable benchmark values without rebasing or a second axis', async () => {
    const root = createRoot(host);
    const btc: QfLineSeries = {
      key: 'btc',
      label: 'BTC',
      isBenchmark: true,
      points: [
        { date: new Date('2026-01-01'), value: -0.5 },
        { date: new Date('2026-01-02'), value: -0.2 },
      ],
    };
    await act(async () =>
      root.render(<LineChart series={[...series, btc]} benchmarkScale="shared" />),
    );
    const option = capturedOptions.at(-1) as {
      series: Array<{
        id: string;
        yAxisIndex: number;
        data: number[][];
        lineStyle: { type: string };
      }>;
      yAxis: unknown[];
    };
    expect(option.yAxis).toHaveLength(1);
    expect(option.series[1]?.yAxisIndex).toBe(0);
    expect(option.series[1]?.data.map((point) => point[1])).toEqual([-0.5, -0.2]);
    expect(option.series[1]?.lineStyle.type).toBe('dashed');
    await act(async () => root.unmount());
  });

  it('repaints series swaps and legend visibility changes without animation', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<LineChart series={series} hiddenSeries={new Set()} height={320} />),
    );
    expect(capturedOptions.at(-1)).toMatchObject({ animation: false });

    await act(async () =>
      root.render(<LineChart series={series} hiddenSeries={new Set(['strategy'])} height={320} />),
    );
    expect(capturedOptions.at(-1)).toMatchObject({ animation: false });

    const swapped: QfLineSeries = {
      key: 'swapped',
      label: 'Swapped',
      points: series[0]?.points ?? [],
    };
    await act(async () => root.render(<LineChart series={[swapped]} height={320} />));
    const swappedOption = capturedOptions.at(-1) as {
      animation: boolean;
      animationDuration?: number;
      series: Array<{ id: string }>;
    };
    expect(swappedOption.animation).toBe(false);
    expect(swappedOption.animationDuration).toBeUndefined();
    expect(swappedOption.series.map((item) => item.id)).toEqual(['swapped']);

    await act(async () => root.unmount());
  });

  it('dims non-hovered series immediately and restores them immediately', async () => {
    const root = createRoot(host);
    const comparisonSeries: QfLineSeries = {
      key: 'comparison',
      label: 'Comparison',
      points: series[0]?.points ?? [],
    };
    await act(async () =>
      root.render(<LineChart series={[...series, comparisonSeries]} height={320} />),
    );

    await act(async () =>
      root.render(
        <LineChart
          series={[...series, comparisonSeries]}
          emphasizedSeries="strategy"
          height={320}
        />,
      ),
    );
    type Patch = Array<{ id: string; lineStyle: { opacity: number } }>;
    const emphasizedPatch = capturedPatches.at(-1) as Patch;
    expect(emphasizedPatch.find((item) => item.id === 'strategy')?.lineStyle.opacity).toBe(1);
    expect(emphasizedPatch.find((item) => item.id === 'comparison')?.lineStyle.opacity).toBe(0.25);

    await act(async () =>
      root.render(<LineChart series={[...series, comparisonSeries]} height={320} />),
    );
    const restoredPatch = capturedPatches.at(-1) as Patch;
    expect(restoredPatch.every((item) => item.lineStyle.opacity === 1)).toBe(true);

    await act(async () => root.unmount());
  });

  it('focuses a series through a style-only patch without rebuilding the option', async () => {
    const root = createRoot(host);
    const comparisonSeries: QfLineSeries = {
      key: 'comparison',
      label: 'Comparison',
      points: series[0]?.points ?? [],
    };
    const stableSeries = [...series, comparisonSeries];
    await act(async () => root.render(<LineChart series={stableSeries} height={320} />));
    const initialOption = capturedOptions.at(-1) as { series: Array<{ data: unknown }> };

    await act(async () =>
      root.render(<LineChart series={stableSeries} emphasizedSeries="strategy" height={320} />),
    );
    expect(capturedOptions.at(-1)).toBe(initialOption);
    const patch = capturedPatches.at(-1) ?? [];
    expect(patch.map((item) => item.id)).toEqual(['strategy', 'comparison']);
    expect(patch.every((item) => !('data' in item))).toBe(true);

    await act(async () => root.unmount());
  });

  it('passes inverse rank axes to ECharts', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<LineChart series={series} height={320} yAxisInverse />));
    const option = capturedOptions.at(-1) as {
      yAxis: Array<{ inverse?: boolean }>;
    };

    expect(option.yAxis[0]?.inverse).toBe(true);

    await act(async () => root.unmount());
  });

  it('renders an isolated observation as a visible point', async () => {
    const root = createRoot(host);
    const isolated: QfLineSeries = {
      key: 'isolated',
      label: 'Isolated observation',
      points: [{ date: new Date('2026-01-01T00:00:00Z'), value: 3.75 }],
    };
    await act(async () => root.render(<LineChart series={[isolated]} height={320} />));
    const option = capturedOptions.at(-1) as {
      series: Array<{ showSymbol: boolean; symbol: string; symbolSize?: number }>;
    };

    expect(option.series[0]).toMatchObject({
      showSymbol: true,
      symbol: 'circle',
      symbolSize: 7,
    });

    await act(async () => root.unmount());
  });

  it('keeps metric axes linear while rendering the hidden benchmark axis logarithmically', async () => {
    const root = createRoot(host);
    const primary = series[0];
    if (!primary) throw new Error('Primary fixture is required');
    const secondary: QfLineSeries = { ...primary, key: 'secondary', axis: 'secondary' };
    const benchmark: QfLineSeries = {
      ...primary,
      key: 'btc',
      isBenchmark: true,
    };
    await act(async () =>
      root.render(
        <LineChart
          series={[...series, secondary, benchmark]}
          benchmarkScaleType="log"
          height={320}
        />,
      ),
    );
    const option = capturedOptions.at(-1) as {
      series: Array<{ id: string; yAxisIndex: number }>;
      yAxis: Array<{ show?: boolean; type?: string }>;
    };
    expect(option.yAxis.map((axis) => axis.type)).toEqual(['value', 'value', 'log']);
    expect(option.yAxis[2]?.show).toBe(false);
    expect(option.series.find((item) => item.id === 'btc')?.yAxisIndex).toBe(2);

    await act(async () => root.unmount());
  });

  it('forces benchmarks onto a hidden axis with a dim dashed semantic-grey style', async () => {
    const root = createRoot(host);
    const primary = series[0];
    if (!primary) throw new Error('Primary fixture is required');
    const benchmark: QfLineSeries = {
      ...primary,
      key: 'benchmark',
      color: '#ff0000',
      isBenchmark: true,
    };

    await act(async () =>
      root.render(<LineChart series={[primary, benchmark]} height={320} visibleSecondaryAxis />),
    );
    const option = capturedOptions.at(-1) as {
      series: Array<{
        id: string;
        lineStyle: { color: string; opacity: number; type: string };
        yAxisIndex: number;
      }>;
      yAxis: Array<{ show?: boolean }>;
    };
    const renderedBenchmark = option.series.find((item) => item.id === 'benchmark');
    expect(renderedBenchmark?.lineStyle).toMatchObject({
      color: QF_DARK_THEME.benchmark,
      opacity: 0.72,
      type: 'dashed',
    });
    expect(renderedBenchmark?.yAxisIndex).toBe(1);
    expect(option.yAxis[1]?.show).toBe(false);

    await act(async () => root.unmount());
  });

  it('indexes a primary-scale benchmark to the strategy and widens the shared domain to it', async () => {
    const root = createRoot(host);
    const day = (n: number) => new Date(Date.UTC(2026, 0, n));
    const strategy: QfLineSeries = {
      key: 'strategy',
      label: 'Strategy',
      points: [2, 3, 4].map((n, i) => ({ date: day(n), value: [2, 2.2, 2.4][i] ?? 0 })),
    };
    const btc: QfLineSeries = {
      key: 'btc',
      label: 'BTC',
      isBenchmark: true,
      points: [1, 2, 3, 4].map((n, i) => ({ date: day(n), value: [90, 100, 150, 50][i] ?? 0 })),
    };
    await act(async () =>
      root.render(<LineChart series={[strategy, btc]} height={320} benchmarkScale="primary" />),
    );
    const option = capturedOptions.at(-1) as {
      series: Array<{ id: string; data: Array<[number, number]> }>;
      yAxis: Array<{ show?: boolean; min?: number; max?: number }>;
    };
    const rebased = option.series.find((item) => item.id === 'btc')?.data ?? [];
    // Starts with the strategy (day 2) at its level 2; BTC +50% then -50% from there.
    expect(rebased.map(([, value]) => value)).toEqual([2, 3, 1]);
    const primary = option.yAxis[0];
    // One domain spans strategy and indexed BTC (1..3), padded 5%.
    expect(primary?.min).toBeCloseTo(0.9);
    expect(primary?.max).toBeCloseTo(3.1);
    expect(option.yAxis[1]).toMatchObject({ show: false, min: primary?.min, max: primary?.max });
    await act(async () => root.unmount());
  });

  it('formats inferred intraday domains as clock time', async () => {
    const root = createRoot(host);
    const intradaySeries: readonly QfLineSeries[] = [
      {
        key: 'intraday',
        label: 'Intraday',
        points: [
          { date: new Date(2026, 7, 30, 9), value: 1 },
          { date: new Date(2026, 7, 30, 10), value: 2 },
        ],
      },
    ];
    await act(async () => root.render(<LineChart series={intradaySeries} height={320} />));
    const option = capturedOptions.at(-1) as {
      xAxis: { axisLabel: { formatter: (value: number) => string } };
    };

    expect(option.xAxis.axisLabel.formatter(new Date(2026, 7, 30, 9, 30).getTime())).toMatch(
      /09.*30/,
    );

    await act(async () => root.unmount());
  });
});
