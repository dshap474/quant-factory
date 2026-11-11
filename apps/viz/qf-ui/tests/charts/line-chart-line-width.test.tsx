/**
 * One line width: every plotted data line draws at QF_CHART_LINE_WIDTH, at rest,
 * under hover emphasis and under legend dimming; reference rules stay hairlines.
 *
 * USAGE:
 *   pnpm test -- line-chart-line-width.test.tsx
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

import { LineChart, type QfLineSeries } from '../../src/charts/charts/LineChart';
import { QF_CHART_LINE_WIDTH, QF_CHART_RULE_WIDTH } from '../../src/charts/core/geometry';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const points = [
  { date: new Date('2026-01-01T00:00:00Z'), value: -1 },
  { date: new Date('2026-01-02T00:00:00Z'), value: 2 },
];

const series: readonly QfLineSeries[] = [
  { key: 'strategy', label: 'Strategy', points },
  { key: 'faded', label: 'Faded', points, opacity: 0.5, interpolation: 'step-end' },
  { key: 'area', label: 'Area', points, area: true },
  { key: 'btc', label: 'BTC', points, isBenchmark: true },
  { key: 'fill', label: 'Fill', points, area: true, showLine: false },
];

interface CapturedSeries {
  id: string;
  lineStyle: { width: number };
  emphasis: { lineStyle: { width: number } };
  markLine?: { lineStyle: { width: number }; data: Array<{ lineStyle?: { width: number } }> };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LineChart line width', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('draws every data line at 1.5px and pins emphasis and dimming to it', async () => {
    expect(QF_CHART_LINE_WIDTH).toBe(1.5);
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <LineChart series={series} height={320} thresholdY={1} emphasizedSeries="strategy" />,
      ),
    );
    const option = capturedOptions.at(-1) as { series: CapturedSeries[] };
    const drawn = option.series.filter((item) => item.id !== 'fill');
    for (const item of drawn) {
      expect(item.lineStyle.width).toBe(QF_CHART_LINE_WIDTH);
      expect(item.emphasis.lineStyle.width).toBe(QF_CHART_LINE_WIDTH);
    }
    expect(option.series.find((item) => item.id === 'fill')?.lineStyle.width).toBe(0);
    const markLine = option.series[0]?.markLine;
    expect(markLine?.lineStyle.width).toBe(QF_CHART_RULE_WIDTH);
    for (const rule of markLine?.data ?? []) {
      if (rule.lineStyle) expect(rule.lineStyle.width).toBe(QF_CHART_RULE_WIDTH);
    }
    await act(async () => root.unmount());
  });
});
