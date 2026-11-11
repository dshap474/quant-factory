/**
 * Contract tests for multi-series mapping into the package line renderer.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/multi-series-line-plot.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import type { LineChartProps } from '../../src/charts/charts/LineChart';
import { MultiSeriesLinePlot } from '../../src/charts/charts/MultiSeriesLinePlot';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('MultiSeriesLinePlot', () => {
  it('maps rank semantics and leaves benchmark placement to the shared renderer', () => {
    const start = new Date('2026-08-01T00:00:00Z');
    const end = new Date('2026-08-02T00:00:00Z');
    const chart = MultiSeriesLinePlot({
      plotWidth: 640,
      plotHeight: 360,
      marginLeft: 72,
      marginTop: 20,
      innerWidth: 544,
      innerHeight: 300,
      xDomain: [start, end],
      leftDomain: [0, 10],
      rightDomain: [0, 1],
      overlayDomain: [110_000, 120_000],
      hiddenSeries: new Set(),
      emphasizedSeries: 'metric',
      series: [
        {
          metric: 'metric',
          axis: 'right',
          label: 'Metric',
          color: '#ffffff',
          points: [
            { date: start, value: 2 },
            { date: end, value: 8 },
          ],
        },
        {
          metric: 'named_control',
          axis: 'left',
          label: 'Named control',
          color: '#aaaaaa',
          isBenchmark: true,
          points: [
            { date: start, value: 4 },
            { date: end, value: 5 },
          ],
        },
      ],
      visibleSeries: [
        {
          metric: 'metric',
          axis: 'right',
          label: 'Metric',
          color: '#ffffff',
          points: [
            { date: start, value: 2 },
            { date: end, value: 8 },
          ],
        },
      ],
      visiblePriceOverlay: {
        id: 'btc',
        label: 'BTC benchmark',
        points: [
          { date: start, value: 112_000 },
          { date: end, value: 118_000 },
        ],
      },
      valueFormat: 'rank',
    }) as ReactElement<LineChartProps>;

    expect(chart.props.series[0]).toMatchObject({ key: 'metric' });
    expect(chart.props.series[0]).not.toHaveProperty('isBenchmark');
    expect(chart.props.series[1]).toMatchObject({
      key: 'named_control',
      isBenchmark: true,
    });
    expect(chart.props.series.at(-1)).toMatchObject({
      key: 'btc',
      isBenchmark: true,
    });
    expect(chart.props.series.at(-1)).not.toHaveProperty('strokeWidth');
    expect(chart.props.series.at(-1)).not.toHaveProperty('axis');
    expect(chart.props.ySecondaryDomain).toEqual([0, 1]);
    expect(chart.props.benchmarkDomain).toEqual([110_000, 120_000]);
    expect(chart.props.benchmarkScaleType).toBe('log');
    expect(chart.props.visibleSecondaryAxis).toBe(true);
    expect(chart.props.yDomain).toEqual([0, 10]);
    expect(chart.props.yAxisInverse).toBe(true);
    expect(chart.props.ySecondaryAxisInverse).toBe(true);
    expect(chart.props.yFormat?.(3)).toBe('3');
    expect(chart.props.emphasizedSeries).toBe('metric');
  });

  it('passes hidden metrics to the renderer for an instant visibility update', () => {
    const start = new Date('2026-08-01T00:00:00Z');
    const end = new Date('2026-08-02T00:00:00Z');
    const hiddenSeries = new Set(['hidden']);
    const chart = MultiSeriesLinePlot({
      plotWidth: 640,
      plotHeight: 360,
      marginLeft: 72,
      marginTop: 20,
      innerWidth: 544,
      innerHeight: 300,
      xDomain: [start, end],
      leftDomain: [0, 10],
      rightDomain: [0, 1],
      overlayDomain: [0, 1],
      hiddenSeries,
      emphasizedSeries: null,
      series: [
        {
          metric: 'hidden',
          axis: 'left',
          label: 'Hidden',
          color: '#ffffff',
          points: [
            { date: start, value: 2 },
            { date: end, value: 8 },
          ],
        },
      ],
      visibleSeries: [],
    }) as ReactElement<LineChartProps>;

    expect(chart.props.series).toHaveLength(1);
    expect(chart.props.hiddenSeries).toBe(hiddenSeries);
  });

  it('maps a named tertiary series to an independent visible axis', () => {
    const date = new Date('2026-08-01T00:00:00Z');
    const chart = MultiSeriesLinePlot({
      plotWidth: 720,
      plotHeight: 405,
      marginLeft: 72,
      marginTop: 20,
      innerWidth: 504,
      innerHeight: 345,
      xDomain: [date, new Date('2026-08-02T00:00:00Z')],
      leftDomain: [-10, 10],
      rightDomain: [-1, 1],
      tertiaryDomain: [90, 110],
      overlayDomain: [0, 1],
      hiddenSeries: new Set(),
      emphasizedSeries: null,
      series: [
        {
          metric: 'price',
          axis: 'tertiary',
          label: 'Price (quote currency)',
          color: '#fff',
          points: [{ date, value: 100 }],
        },
      ],
      visibleSeries: [
        {
          metric: 'price',
          axis: 'tertiary',
          label: 'Price (quote currency)',
          color: '#fff',
          points: [{ date, value: 100 }],
        },
      ],
      tertiaryValueFormat: 'number',
      axisLabels: { tertiary: 'Price (quote currency)' },
    }) as ReactElement<LineChartProps>;

    expect(chart.props.series[0]).toMatchObject({ axis: 'tertiary' });
    expect(chart.props.series[0]).not.toHaveProperty('isBenchmark');
    expect(chart.props.yTertiaryDomain).toEqual([90, 110]);
    expect(chart.props.yTertiaryAxisName).toBe('Price (quote currency)');
    expect(chart.props.visibleTertiaryAxis).toBe(true);
  });
});
