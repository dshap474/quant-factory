/**
 * Unit tests for package-owned multi-series chart model behavior.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/multi-series-model.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  axisDomain,
  findNearestPoint,
  formatDateTick,
  formatTooltipValue,
  formatYAxis,
  lttb,
  type MultiSeriesPlotSeries,
  type MultiSeriesPoint,
  paletteMetricColors,
  parseMultiSeries,
  upperBound,
  valueToPlotY,
} from '../../src/charts/charts/multiSeriesModel';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function series(n: number): MultiSeriesPoint[] {
  return Array.from({ length: n }, (_, i) => ({
    date: new Date(Date.UTC(2020, 0, 1 + i)),
    value: Math.sin(i / 8) * 10 + i * 0.01,
  }));
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('formatYAxis / formatTooltipValue', () => {
  it('formats large magnitudes with suffixes', () => {
    expect(formatYAxis(1_500_000_000)).toBe('1.5B');
    expect(formatYAxis(2_500_000)).toBe('2.5M');
    expect(formatYAxis(12_500)).toBe('12.5K');
  });

  it('formats small tooltip values with precision', () => {
    expect(formatTooltipValue(0.001234)).toBe('0.001234');
    expect(formatTooltipValue(12.34567)).toBe('12.3457');
  });

  it('formats PnL axes and tooltips as dollars', () => {
    expect(formatYAxis(-6_270.75, 'money')).toBe('-$6.3K');
    expect(formatTooltipValue(-6_270.75, 'money')).toBe('-$6,270.75');
  });

  it('formats ratio values as actual percentages', () => {
    expect(formatYAxis(0.012345, 'percent')).toBe('1.23%');
    expect(formatYAxis(-0.0042, 'percent')).toBe('-0.42%');
    expect(formatTooltipValue(0.012345, 'percent')).toBe('1.2345%');
  });

  it('formats signed percent deltas and percentage-point values without clamping semantics', () => {
    expect(formatYAxis(-0.031, 'percent-delta')).toBe('-3.1%');
    expect(formatTooltipValue(-0.031, 'percent-delta')).toBe('-3.1000%');
    expect(formatYAxis(42.37, 'percent-points')).toBe('42.37%');
    expect(formatTooltipValue(-5.53, 'percent-points')).toBe('-5.5300%');
    expect(formatYAxis(1.234, 'percentage-points')).toBe('1.23 pp');
    expect(formatTooltipValue(-0.125, 'percentage-points')).toBe('-0.1250 pp');
  });

  it('labels basis-point axes and tooltips explicitly', () => {
    expect(formatYAxis(42.37, 'basis-points')).toBe('42.37 bp');
    expect(formatTooltipValue(-5.53, 'basis-points')).toBe('-5.53 bp');
  });

  it('formats ETF flow values reported in USD millions as actual dollars', () => {
    expect(formatYAxis(296, 'money-millions')).toBe('$296M');
    expect(formatYAxis(48_516.6, 'money-millions')).toBe('$48.52B');
    expect(formatTooltipValue(-296, 'money-millions')).toBe('-$296,000,000');
  });

  it('formats ranks without unnecessary decimal places', () => {
    expect(formatYAxis(3, 'rank')).toBe('3');
    expect(formatTooltipValue(12.5, 'rank')).toBe('12.5');
    expect(formatTooltipValue(-7, 'rank-delta')).toBe('-7');
  });
});

describe('axisDomain', () => {
  const plottedSeries = [
    {
      metric: 'breadth',
      axis: 'left' as const,
      label: 'Breadth',
      color: '#fff',
      points: [
        { date: new Date('2026-08-01T00:00:00Z'), value: 0 },
        { date: new Date('2026-08-02T00:00:00Z'), value: 1 },
      ],
    },
  ];

  it('fixes percentage axes to the complete 0%-100% range', () => {
    expect(axisDomain(plottedSeries, 'left', 'percent')).toEqual([0, 1]);
  });

  it('retains padded data domains for non-percentage axes', () => {
    expect(axisDomain(plottedSeries, 'left', 'number')).toEqual([-0.08, 1.08]);
    expect(axisDomain(plottedSeries, 'left', 'percent-delta')).toEqual([-0.08, 1.08]);
    expect(axisDomain(plottedSeries, 'left', 'percent-points')).toEqual([-0.08, 1.08]);
  });

  it('keeps benchmark values out of visible metric-axis domains', () => {
    const benchmark: MultiSeriesPlotSeries = {
      metric: 'benchmark',
      axis: 'left',
      label: 'Benchmark',
      color: '#aaa',
      isBenchmark: true,
      points: [{ date: new Date('2026-08-01T00:00:00Z'), value: 10_000 }],
    };

    expect(axisDomain([...plottedSeries, benchmark], 'left', 'number')).toEqual([-0.08, 1.08]);
  });

  it('uses ordinal and symmetric domains for ranks and rank deltas', () => {
    const ranks: MultiSeriesPlotSeries[] = [
      {
        metric: 'rank',
        axis: 'left',
        label: 'Rank',
        color: '#fff',
        points: [
          { date: new Date('2026-08-01T00:00:00Z'), value: 1 },
          { date: new Date('2026-08-02T00:00:00Z'), value: 125 },
        ],
      },
    ];
    const deltas: MultiSeriesPlotSeries[] = [
      {
        metric: 'delta',
        axis: 'left',
        label: 'Delta',
        color: '#fff',
        points: [
          { date: new Date('2026-08-01T00:00:00Z'), value: -12 },
          { date: new Date('2026-08-02T00:00:00Z'), value: 20 },
        ],
      },
    ];

    expect(axisDomain(ranks, 'left', 'rank')).toEqual([1, 125]);
    expect(axisDomain(deltas, 'left', 'rank-delta')).toEqual([-20, 20]);
  });
});

describe('formatDateTick', () => {
  it('uses time labels under two days and day-month labels above', () => {
    const value = new Date(2024, 5, 15, 12, 34);
    const intraday: [Date, Date] = [new Date(2024, 5, 15, 10), new Date(2024, 5, 15, 16)];
    const multiDay: [Date, Date] = [new Date(2024, 5, 1), new Date(2024, 5, 8)];
    const long: [Date, Date] = [new Date(2024, 0, 1), new Date(2024, 11, 1)];

    expect(formatDateTick(value, intraday)).toMatch(/12.*34/);
    expect(formatDateTick(value, multiDay)).toBe('15 Jun');
    expect(formatDateTick(value, long)).toBe('15 Jun');
  });

  it('falls back deterministically for invalid or degenerate input', () => {
    const value = new Date(2024, 5, 15, 12, 34);

    expect(formatDateTick(value, [value, value])).toBe('15 Jun');
    expect(formatDateTick(value, [new Date(Number.NaN), value])).toBe('15 Jun');
    expect(formatDateTick(new Date(Number.NaN), null)).toBe('');
  });
});

describe('upperBound / findNearestPoint / lttb', () => {
  it('normalizes source points into chronological order', () => {
    const [normalized] = parseMultiSeries(
      [
        {
          metric: 'value',
          axis: 'left',
          label: 'Value',
          points: [
            { x: '2026-08-02T00:00:00Z', y: 2 },
            { x: '2026-08-01T00:00:00Z', y: 1 },
          ],
        },
      ],
      {},
      '#fff',
    );

    expect(normalized?.points.map((point) => point.value)).toEqual([1, 2]);
  });

  it('preserves date-only values as local calendar dates', () => {
    const [normalized] = parseMultiSeries(
      [
        {
          metric: 'daily',
          axis: 'left',
          label: 'Daily',
          points: [{ x: '2026-09-01', y: 1 }],
        },
      ],
      {},
      '#fff',
    );

    expect(normalized?.points[0]?.date.getFullYear()).toBe(2026);
    expect(normalized?.points[0]?.date.getMonth()).toBe(8);
    expect(normalized?.points[0]?.date.getDate()).toBe(1);
  });

  it('upperBound returns first index with date > target', () => {
    const points = series(5);
    const third = points[2];
    expect(third).toBeDefined();
    if (!third) return;
    expect(upperBound(points, third.date.getTime())).toBe(3);
  });

  it('findNearestPoint returns closest sample', () => {
    const points = series(10);
    const mid = points[4];
    expect(mid).toBeDefined();
    if (!mid) return;
    const hit = findNearestPoint(points, new Date(mid.date.getTime() + 1000));
    expect(hit?.date.getTime()).toBe(mid.date.getTime());
  });

  it('findNearestPoint rejects a sample outside an explicit distance limit', () => {
    const points = series(2);
    const oneDay = 24 * 60 * 60 * 1000;

    expect(findNearestPoint(points, new Date('2020-02-01T00:00:00Z'), 4 * oneDay)).toBeNull();
  });

  it('lttb downsamples while preserving endpoints', () => {
    const points = series(500);
    const sampled = lttb(points, 50);
    expect(sampled.length).toBe(50);
    expect(sampled[0]).toEqual(points[0]);
    expect(sampled[sampled.length - 1]).toEqual(points[points.length - 1]);
  });

  it('lttb is a no-op below threshold', () => {
    const points = series(20);
    expect(lttb(points, 50)).toBe(points);
  });

  it('preserves null source gaps through parsing and chart downsampling', () => {
    const [normalized] = parseMultiSeries(
      [
        {
          metric: 'price',
          axis: 'tertiary',
          label: 'Price',
          points: Array.from({ length: 500 }, (_, index) => ({
            x: new Date(Date.UTC(2026, 0, index + 1)),
            y: index === 250 ? null : index,
          })),
        },
      ],
      {},
      '#fff',
    );

    expect(normalized?.points[250]?.value).toBeNull();
    expect(normalized ? lttb(normalized.points, 50) : []).toHaveLength(500);
  });
});

describe('valueToPlotY', () => {
  it('places linear values from the bottom of the plot', () => {
    const axis = { domain: [0, 100] as const, scale: 'linear' as const, inverse: false };
    expect(valueToPlotY(0, axis, 20, 200)).toBe(220);
    expect(valueToPlotY(25, axis, 20, 200)).toBe(170);
    expect(valueToPlotY(100, axis, 20, 200)).toBe(20);
  });

  it('places log values geometrically and flips inverted axes', () => {
    const log = { domain: [10, 1000] as const, scale: 'log' as const, inverse: false };
    expect(valueToPlotY(100, log, 0, 200)).toBeCloseTo(100);
    const rank = { domain: [1, 5] as const, scale: 'linear' as const, inverse: true };
    expect(valueToPlotY(1, rank, 0, 200)).toBe(0);
  });

  it('refuses values off the axis', () => {
    const axis = { domain: [0, 100] as const, scale: 'linear' as const, inverse: false };
    expect(valueToPlotY(120, axis, 0, 200)).toBeNull();
    expect(valueToPlotY(-1, { ...axis, scale: 'log' }, 0, 200)).toBeNull();
  });
});

describe('paletteMetricColors', () => {
  it('gives the first series the primary colour and later ones palette slots, skipping benchmarks', () => {
    expect(
      paletteMetricColors(
        [
          { metric: 'strategy' },
          { metric: 'btc', isBenchmark: true },
          { metric: 'control' },
          { metric: 'hedge' },
        ],
        'var(--qf-chart-series-primary)',
      ),
    ).toEqual({
      strategy: 'var(--qf-chart-series-primary)',
      control: 'var(--qf-chart-2)',
      hedge: 'var(--qf-chart-3)',
    });
  });
});
