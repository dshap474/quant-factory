/**
 * PriceProfileChart: price path, stepped levels, annotations and the side profile panel.
 *
 * USAGE:
 *   pnpm test -- price-profile-chart.test.tsx
 */

// --------------------------------------------------------------------------- #
// Mocks
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const capturedOptions = vi.hoisted<Array<Record<string, unknown>>>(() => []);

vi.mock('../../src/charts/core/QfChart', () => ({
  QfChart: ({ option }: { option: Record<string, unknown> }) => {
    capturedOptions.push(option);
    return <div data-testid="qf-chart" />;
  },
}));

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  breakLineGaps,
  buildPriceProfileOption,
  formatPriceProfileTime,
  PriceProfileChart,
  type PriceProfileChartProps,
  type PriceProfileModel,
  priceProfileExtent,
  priceProfileTooltipItems,
} from '../../src/charts/charts/PriceProfileChart';
import { QF_CHART_LINE_WIDTH, QF_CHART_RULE_WIDTH } from '../../src/charts/core/geometry';
import type { QfChartTheme } from '../../src/charts/hooks/useChartTheme';
import { chartColor, withOpacity } from '../../src/charts/theme/chartColor';
import { resolveCssColor } from '../../src/charts/theme/tokens';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const MINUTE = 60_000;
const OPEN = Date.UTC(2025, 0, 2);
const CLOSE = OPEN + 24 * 60 * MINUTE;

const theme: QfChartTheme = {
  axis: 'rgb(1, 1, 1)',
  axisFontSize: 11,
  background: 'rgb(2, 2, 2)',
  benchmark: 'rgb(3, 3, 3)',
  crosshair: 'rgb(4, 4, 4)',
  focus: 'rgb(5, 5, 5)',
  fontFamily: 'sans-serif',
  frame: 'rgb(6, 6, 6)',
  grid: 'rgb(7, 7, 7)',
  gridOpacity: 1,
  lineWidth: QF_CHART_LINE_WIDTH,
  palette: ['rgb(8, 8, 8)'],
  tooltipBackground: 'rgb(9, 9, 9)',
  tooltipBorder: 'rgb(10, 10, 10)',
  tooltipText: 'rgb(11, 11, 11)',
};

const props: Omit<PriceProfileChartProps, 'ariaLabel'> = {
  xDomain: [OPEN, CLOSE],
  maxGap: MINUTE,
  timeZone: 'utc',
  price: {
    key: 'close',
    label: 'Close',
    color: 'rgb(20, 20, 20)',
    points: [
      [OPEN + MINUTE, 100.5],
      [OPEN + 2 * MINUTE, 101],
      [OPEN + 5 * MINUTE, 102],
    ],
  },
  levels: [
    {
      key: 'mid',
      label: 'Developing mid',
      endLabel: 'MID',
      color: 'rgb(30, 30, 30)',
      dashedUntil: CLOSE - 60 * MINUTE,
      points: [
        [OPEN + MINUTE, 100],
        [CLOSE - 60 * MINUTE, 101],
        [CLOSE, 101.5],
      ],
    },
  ],
  segments: [
    {
      key: 'prior',
      label: 'Prior mid',
      value: 95.5,
      from: CLOSE - 14 * MINUTE,
      to: CLOSE,
      color: 'rgb(40, 40, 40)',
      style: 'dotted',
      weight: 'level',
      muted: true,
      text: 'Prior mid',
      textPosition: 'end',
    },
    {
      key: 'trigger',
      label: 'Trigger',
      value: 101,
      from: OPEN,
      to: OPEN + 120 * MINUTE,
      color: 'rgb(50, 50, 50)',
      style: 'dashed',
      weight: 'guide',
      text: 'trigger',
      textPosition: 'start',
    },
  ],
  timeGuides: [
    { key: 'a', at: OPEN, label: 'A' },
    { key: 'b', at: OPEN + 8 * 60 * MINUTE, label: 'B' },
  ],
  markers: [
    {
      key: 'm1',
      time: OPEN + MINUTE,
      value: 100.5,
      label: 'one',
      color: 'rgb(60, 60, 60)',
      labelPosition: 'bottom',
    },
    {
      key: 'm2',
      time: OPEN + 2 * MINUTE,
      value: 105,
      label: 'two',
      color: 'rgb(70, 70, 70)',
      labelPosition: 'top',
    },
  ],
  profiles: [
    {
      key: 'day',
      label: 'Day profile',
      color: 'rgb(80, 80, 80)',
      rowSize: 1,
      band: [99, 103],
      rows: [
        [99.5, 3],
        [100.5, 7],
        [104.5, 8],
      ],
    },
    {
      key: 'prior',
      label: 'Prior profile',
      color: 'rgb(90, 90, 90)',
      rowSize: 1,
      variant: 'outline',
      rows: [[94.5, 2]],
    },
  ],
};

const model: PriceProfileModel = { ...props, hiddenSeries: new Set() };

interface Series {
  id: string;
  type: string;
  data: Array<[number, number | null]>;
  lineStyle?: { width: number; type: unknown; color: string };
  endLabel?: { show: boolean; formatter: string };
  markLine?: { data: unknown[] };
  markPoint?: { data: Array<Record<string, unknown>> };
  renderItem?: (params: unknown, api: unknown) => { style: Record<string, unknown> };
}

interface Option {
  useUTC: boolean;
  series: Series[];
  xAxis: Array<{ min: number; max: number; axisLabel: { formatter?: (v: number) => string } }>;
  yAxis: Array<{
    min: number;
    max: number;
    axisPointer: { show?: boolean; label?: { show: boolean; formatter: (p: unknown) => string } };
  }>;
  tooltip: {
    axisPointer: { type: string; lineStyle: { color: string; type: unknown; width: number } };
    formatter: (params: unknown) => string;
  };
}

function build(overrides: Partial<PriceProfileModel> = {}): Option {
  return buildPriceProfileOption({ ...model, ...overrides }, theme) as unknown as Option;
}

function series(option: Option, id: string): Series {
  const found = option.series.find((item) => item.id === id);
  if (!found) throw new Error(`missing series ${id}`);
  return found;
}

// --------------------------------------------------------------------------- #
// Pure helpers
// --------------------------------------------------------------------------- #

describe('PriceProfileChart helpers', () => {
  it('breaks a line with a null one gap after a missing interval', () => {
    expect(breakLineGaps(props.price.points, MINUTE)).toEqual([
      [OPEN + MINUTE, 100.5],
      [OPEN + 2 * MINUTE, 101],
      [OPEN + 3 * MINUTE, null],
      [OPEN + 5 * MINUTE, 102],
    ]);
    expect(breakLineGaps(props.price.points, undefined)).toHaveLength(3);
  });

  it('pads one shared price extent over every plotted value', () => {
    const [low, high] = priceProfileExtent(model);
    // 94.5 (prior row) .. 105 (marker) padded by 5% of the 10.5 range.
    expect(low).toBeCloseTo(94.5 - 0.525);
    expect(high).toBeCloseTo(105 + 0.525);
  });

  it('formats the clock in UTC regardless of the runtime time zone', () => {
    expect(formatPriceProfileTime(OPEN + 61 * MINUTE, 'utc')).toBe('01:01');
    expect(formatPriceProfileTime(OPEN + 61 * MINUTE, 'utc', true)).toBe('2025-01-02 01:01 UTC');
  });
});

// --------------------------------------------------------------------------- #
// Option
// --------------------------------------------------------------------------- #

describe('buildPriceProfileOption', () => {
  it('draws the price and every level at the one data line width', () => {
    const option = build();
    const price = series(option, 'price');
    expect(price.lineStyle?.width).toBe(QF_CHART_LINE_WIDTH);
    expect(price.data).toContainEqual([OPEN + 3 * MINUTE, null]);
    for (const item of option.series.filter((entry) => entry.type === 'line' && entry.lineStyle)) {
      expect(item.lineStyle?.width).toBe(QF_CHART_LINE_WIDTH);
    }
  });

  it('dashes a level up to its switch time and draws it solid from there', () => {
    const option = build();
    const dashed = series(option, 'level:mid:dashed');
    const solid = series(option, 'level:mid:solid');
    expect(dashed.lineStyle?.type).toEqual([4, 4]);
    // The missing minutes after the first point break the line with a null.
    expect(dashed.data).toEqual([
      [OPEN + MINUTE, 100],
      [OPEN + 2 * MINUTE, null],
      [CLOSE - 60 * MINUTE, 101],
    ]);
    expect(solid.lineStyle?.type).toBe('solid');
    expect(solid.data).toEqual([
      [CLOSE - 60 * MINUTE, 101],
      [CLOSE - 59 * MINUTE, null],
      [CLOSE, 101.5],
    ]);
    expect(solid.endLabel).toMatchObject({ show: true, formatter: 'MID' });
  });

  it('weights level segments as data lines and guides as rules', () => {
    const marks = series(build(), 'annotations').markLine?.data as Array<
      | [{ lineStyle: { width: number; type: unknown }; label: { position: string } }, unknown]
      | { xAxis: number; lineStyle: { width: number; type: string }; label: { position: string } }
    >;
    const [prior, trigger, ...guides] = marks as [
      [{ lineStyle: { width: number; type: unknown }; label: { position: string } }, unknown],
      [{ lineStyle: { width: number; type: unknown }; label: { position: string } }, unknown],
      ...Array<{
        xAxis: number;
        lineStyle: { width: number; type: string };
        label: { position: string };
      }>,
    ];
    expect(prior[0].lineStyle).toMatchObject({
      width: QF_CHART_LINE_WIDTH,
      type: 'dotted',
      color: resolveCssColor(withOpacity('rgb(40, 40, 40)', 0.72)),
    });
    expect(prior[0].label.position).toBe('end');
    expect(trigger[0].lineStyle).toMatchObject({
      width: QF_CHART_RULE_WIDTH,
      type: [4, 4],
      color: 'rgb(50, 50, 50)',
    });
    expect(trigger[0].label.position).toBe('start');
    expect(guides.map((guide) => guide.xAxis)).toEqual([OPEN, OPEN + 8 * 60 * MINUTE]);
    for (const guide of guides) {
      expect(guide.lineStyle).toMatchObject({ width: QF_CHART_RULE_WIDTH, type: 'dotted' });
      expect(guide.label.position).toBe('insideEndTop');
    }
  });

  it('gives unstyled annotations qf defaults instead of the engine 2px palette line', () => {
    const annotations = series(build(), 'annotations') as Series & {
      markLine: { lineStyle: { width: number; color: string } };
    };
    expect(annotations.lineStyle).toMatchObject({ width: QF_CHART_LINE_WIDTH, color: theme.axis });
    expect(annotations.markLine.lineStyle).toEqual({
      color: theme.crosshair,
      width: QF_CHART_RULE_WIDTH,
    });
  });

  it('keeps each marker in its own colour and label position', () => {
    const points = series(build(), 'annotations').markPoint?.data ?? [];
    expect(points).toHaveLength(2);
    expect(points[0]).toMatchObject({
      coord: [OPEN + MINUTE, 100.5],
      itemStyle: { color: 'rgb(60, 60, 60)' },
      label: { formatter: 'one', position: 'bottom' },
    });
    expect(points[1]).toMatchObject({ label: { formatter: 'two', position: 'top' } });
  });

  it('shares one price domain across both panels and opens on the brushed window', () => {
    const option = build({ window: [OPEN - MINUTE, OPEN + 30 * MINUTE] });
    expect(option.yAxis[0]?.min).toBe(option.yAxis[1]?.min);
    expect(option.yAxis[0]?.max).toBe(option.yAxis[1]?.max);
    expect(option.xAxis[0]).toMatchObject({ min: OPEN, max: OPEN + 30 * MINUTE });
    expect(option.useUTC).toBe(true);
    expect(option.xAxis[0]?.axisLabel.formatter?.(OPEN + 16 * 60 * MINUTE)).toBe('16:00');
  });

  it('fills band rows, outlines comparison rows and empties hidden profiles', () => {
    // The chart owns profile opacities: band rows in the profile colour, the rest in
    // the neutral label tone, an outlined profile as a faint stroke over a faint fill.
    const option = build();
    const api = (price: number, mass: number) => ({
      value: (dim: number) => (dim === 0 ? price : mass),
      coord: ([x, y]: [number, number]) => [x, y],
    });
    const day = series(option, 'profile:day');
    expect(day.renderItem?.({}, api(100.5, 7)).style).toEqual({
      fill: resolveCssColor(withOpacity('rgb(80, 80, 80)', 0.55)),
    });
    expect(day.renderItem?.({}, api(104.5, 8)).style).toEqual({
      fill: resolveCssColor(withOpacity(chartColor('label'), 0.35)),
    });
    const prior = series(option, 'profile:prior');
    expect(prior.renderItem?.({}, api(94.5, 2)).style).toEqual({
      fill: resolveCssColor(withOpacity('rgb(90, 90, 90)', 0.05)),
      stroke: resolveCssColor(withOpacity('rgb(90, 90, 90)', 0.58)),
      lineWidth: QF_CHART_RULE_WIDTH,
    });
    const hidden = build({ hiddenSeries: new Set(['day', 'close']) });
    expect(series(hidden, 'profile:day').data).toEqual([]);
    expect(series(hidden, 'price').data).toEqual([]);
    expect(series(hidden, 'annotations').markPoint?.data).toHaveLength(2);
  });

  it('uses the qf dashed crosshair and pins the price to the value axis', () => {
    const option = build();
    expect(option.tooltip.axisPointer.type).toBe('cross');
    expect(option.tooltip.axisPointer.lineStyle).toEqual({
      color: theme.crosshair,
      width: QF_CHART_RULE_WIDTH,
      type: [4, 4],
    });
    const label = option.yAxis[0]?.axisPointer.label;
    expect(label?.show).toBe(true);
    expect(label?.formatter({ value: 101.25 })).toBe('101.25');
    expect(option.yAxis[1]?.axisPointer.show).toBe(false);
  });
});

// --------------------------------------------------------------------------- #
// Tooltip
// --------------------------------------------------------------------------- #

describe('priceProfileTooltipItems', () => {
  it('lists the price, then each level at its nearest drawn point, with swatches', () => {
    const at = CLOSE - 30 * MINUTE;
    const items = priceProfileTooltipItems(
      [
        { seriesId: 'price', axisValue: at, color: 'rgb(20, 20, 20)', value: [at, 100] },
        {
          seriesId: 'level:mid:dashed',
          axisValue: at,
          color: 'rgb(30, 30, 30)',
          value: [CLOSE - 60 * MINUTE, 101],
        },
        {
          seriesId: 'level:mid:solid',
          axisValue: at,
          color: 'rgb(30, 30, 30)',
          value: [CLOSE, 101.5],
        },
      ],
      model,
    );
    expect(items).toEqual([
      { label: 'Close', value: '100', swatch: 'rgb(20, 20, 20)' },
      { label: 'Developing mid', value: '101', swatch: 'rgb(30, 30, 30)' },
    ]);
  });

  it('renders the qf tooltip with rounded-square swatches and the UTC time', () => {
    const html = build().tooltip.formatter([
      {
        seriesId: 'price',
        axisValue: OPEN + MINUTE,
        color: 'rgb(20, 20, 20)',
        value: [OPEN + MINUTE, 100.5],
      },
    ]);
    expect(html).toContain('class="qf-echarts-tooltip"');
    expect(html).toContain('2025-01-02 00:01 UTC');
    expect(html).toContain('class="tooltip-swatch" style="--tooltip-swatch:rgb(20, 20, 20)"');
  });
});

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

describe('PriceProfileChart', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('opens on the focus window and lists the price and profiles in the legend rail', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <PriceProfileChart
          ariaLabel="Session"
          {...props}
          focusWindow={[OPEN + 10 * MINUTE, OPEN + 130 * MINUTE]}
        />,
      ),
    );
    const option = capturedOptions.at(-1) as unknown as Option;
    expect(option.xAxis[0]).toMatchObject({ min: OPEN + 10 * MINUTE, max: OPEN + 130 * MINUTE });
    const legend = [...host.querySelectorAll('.chart-legend-toggle')].map((node) =>
      node.getAttribute('aria-label'),
    );
    expect(legend).toEqual(['Hide Close', 'Hide Day profile', 'Hide Prior profile']);
    expect(host.querySelector('.qf-brush')).not.toBeNull();
    await act(async () => root.unmount());
  });
});
