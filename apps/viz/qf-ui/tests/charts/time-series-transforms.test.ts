/**
 * Unit tests for package-owned Z-score and EMA chart transformations.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/time-series-transforms.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import type {
  MultiSeriesPlotSeries,
  MultiSeriesPoint,
} from '../../src/charts/charts/multiSeriesModel';
import {
  applyTimeSeriesTransforms,
  exponentialMovingAverage,
  trailingZScore,
  transformedValueFormat,
} from '../../src/charts/charts/timeSeriesTransforms';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function points(values: readonly number[]): MultiSeriesPoint[] {
  return values.map((value, index) => ({
    date: new Date(Date.UTC(2026, 0, index + 1)),
    value,
  }));
}

function plotSeries(values: readonly number[], isBenchmark = false): MultiSeriesPlotSeries {
  return {
    metric: isBenchmark ? 'benchmark' : 'metric',
    axis: 'left',
    label: isBenchmark ? 'Benchmark' : 'Metric',
    color: '#fff',
    ...(isBenchmark ? { isBenchmark: true } : {}),
    points: points(values),
  };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('time-series transforms', () => {
  it('calculates an inclusive trailing population Z-score after warm-up', () => {
    const transformed = trailingZScore(points([1, 2, 3, 4, 5]), 3);
    expect(transformed).toHaveLength(2);
    expect(transformed[0]?.date).toEqual(new Date(Date.UTC(2026, 0, 4)));
    expect(transformed[0]?.value).toBeCloseTo(Math.sqrt(1.5));
    expect(transformed[1]?.value).toBeCloseTo(Math.sqrt(1.5));
  });

  it('maps a constant trailing window to a neutral Z-score', () => {
    expect(trailingZScore(points([5, 5, 5, 5]), 3)[0]?.value).toBe(0);
  });

  it('uses elapsed calendar days rather than treating missing dates as rows', () => {
    const sparse = [
      { date: new Date('2026-01-01T00:00:00Z'), value: 1 },
      { date: new Date('2026-01-20T00:00:00Z'), value: 2 },
      { date: new Date('2026-01-31T00:00:00Z'), value: 3 },
    ];
    const transformed = trailingZScore(sparse, 30);
    expect(transformed).toHaveLength(1);
    expect(transformed[0]?.value).toBe(1);
  });

  it('plots EMA only after warm-up and seeds it from the completed trailing window', () => {
    const transformed = exponentialMovingAverage(points([1, 2, 3, 4, 5]), 3);
    expect(transformed.map((point) => point.date)).toEqual([
      new Date(Date.UTC(2026, 0, 4)),
      new Date(Date.UTC(2026, 0, 5)),
    ]);
    expect(transformed.map((point) => point.value)).toEqual([3, 4]);
  });

  it('returns no EMA values when the series does not cover the requested window', () => {
    expect(exponentialMovingAverage(points([1, 2, 3]), 3)).toEqual([]);
  });

  it('uses available hidden history to seed EMA at the first display point', () => {
    const history = points([1, 2, 3, 4, 5]);
    const visible = plotSeries([4, 5]);
    visible.points = history.slice(3);
    visible.transformHistory = history.slice(0, 3);

    const [transformed] = applyTimeSeriesTransforms([visible], { zScore: null, ema: 365 });
    expect(transformed?.points[0]?.date).toEqual(history[3]?.date);
    expect(transformed?.points[0]?.value).toBe(2.5);
    expect(transformed?.points).toHaveLength(2);
  });

  it('applies Z-score before EMA while leaving benchmark series raw', () => {
    const metric = plotSeries(Array.from({ length: 35 }, (_, index) => index ** 2));
    const benchmark = plotSeries([100, 101, 102], true);
    const transformed = applyTimeSeriesTransforms([metric, benchmark], { zScore: 30, ema: 30 });
    const expected = exponentialMovingAverage(trailingZScore(metric.points, 30), 30);
    expect(transformed[0]?.points).toEqual(expected);
    expect(transformed[1]).toBe(benchmark);
  });

  it('keeps source formatting until Z-score mode is active', () => {
    expect(transformedValueFormat('percent', { zScore: null, ema: 30 })).toBe('percent');
    expect(transformedValueFormat('percent', { zScore: 90, ema: null })).toBe('number');
  });
});
