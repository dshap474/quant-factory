/** Portfolio drawdown known answers and linked controls. USAGE: pnpm test -- portfolio-drawdown-chart. */

// --------------------------------------------------------------------------- #
// Imports and renderer observation
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';
import type { LineChartProps } from '../../src/charts/charts/LineChart';
import {
  PortfolioDrawdownChart,
  portfolioDrawdown,
} from '../../src/charts/charts/PortfolioDrawdownChart';
import type { BrushBarProps } from '../../src/charts/components/BrushBar';

const captured = vi.hoisted(() => ({
  panes: {} as Record<string, LineChartProps>,
  brush: null as BrushBarProps | null,
}));
vi.mock('../../src/charts/charts/LineChart', () => ({
  LineChart: (props: LineChartProps) => {
    captured.panes[props.ariaLabel ?? ''] = props;
    return <div />;
  },
}));
vi.mock('../../src/charts/components/BrushBar', () => ({
  BrushBar: (props: BrushBarProps) => {
    captured.brush = props;
    return <div />;
  },
}));

const date = (day: number) => new Date(Date.UTC(2026, 0, day));
const points = (values: (number | null)[]) =>
  values.map((value, index) => ({ date: date(index + 1), value }));

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('portfolio drawdown', () => {
  it('uses the running peak, preserves gaps and records recovery', () => {
    const actual = portfolioDrawdown(points([100, 125, null, 100, 150, 120, 0, -15])).map(
      (point) => point.value,
    );
    expect(actual.slice(0, 3)).toEqual([0, 0, null]);
    expect(actual[3]).toBeCloseTo(-0.2);
    expect(actual[4]).toBe(0);
    expect(actual[5]).toBeCloseTo(-0.2);
    expect(actual[6]).toBe(-1);
    expect(actual[7]).toBeCloseTo(-1.1);
    expect(
      portfolioDrawdown(points([0, null, Number.NaN, -5, 100])).map((point) => point.value),
    ).toEqual([null, null, null, null, 0]);
  });

  it('keeps benchmark identity out of the legend on both shared-scale panes', async () => {
    const host = document.createElement('div');
    document.body.append(host);
    const root = createRoot(host);
    try {
      await act(async () =>
        root.render(
          <PortfolioDrawdownChart
            series={[
              {
                metric: 'fund',
                label: 'v002',
                axis: 'left',
                points: [
                  { x: date(1), y: 100 },
                  { x: date(2), y: 120 },
                ],
              },
              {
                metric: 'btc',
                label: 'BTC',
                axis: 'left',
                isBenchmark: true,
                points: [
                  { x: date(1), y: 100 },
                  { x: date(2), y: 80 },
                ],
              },
            ]}
          />,
        ),
      );
      expect(host.querySelector('[aria-label="Hide v002"]')).not.toBeNull();
      expect(host.querySelector('[aria-label="Hide BTC"]')).toBeNull();
      for (const name of ['Portfolio value', 'Drawdown from peak']) {
        expect(captured.panes[name]?.series[1]?.isBenchmark).toBe(true);
        expect(captured.panes[name]?.benchmarkScale).toBe('shared');
      }
      expect(captured.panes['Drawdown from peak']?.series[1]?.points[1]?.value).toBeCloseTo(-0.2);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });

  it('keeps the pre-zoom peak and synchronizes legend visibility across both panes', async () => {
    const host = document.createElement('div');
    document.body.append(host);
    const root = createRoot(host);
    try {
      await act(async () =>
        root.render(
          <PortfolioDrawdownChart
            series={[
              {
                metric: 'fund',
                label: 'Fund',
                axis: 'left',
                points: [100, 200, 150, 160, 180].map((y, index) => ({ x: date(index + 1), y })),
              },
            ]}
            metricColors={{ fund: 'var(--qf-chart-series-primary)' }}
          />,
        ),
      );
      expect(host.querySelectorAll('.qf-multi-pane-chart-pane')).toHaveLength(2);
      await act(async () => captured.brush?.onDomainChange?.([date(4), date(5)]));
      const lower = captured.panes['Drawdown from peak'];
      expect(
        lower?.series[0]?.points.find((point) => point.date.getTime() === date(4).getTime())?.value,
      ).toBeCloseTo(-0.2);
      expect(lower?.yDomain?.[1]).toBe(0);
      expect(lower?.series[0]?.color).toBe(captured.panes['Portfolio value']?.series[0]?.color);
      const toggle = host.querySelector<HTMLButtonElement>('button[aria-label="Hide Fund"]');
      expect(toggle).not.toBeNull();
      await act(async () => toggle?.click());
      expect(captured.panes['Portfolio value']?.hiddenSeries?.has('fund')).toBe(true);
      expect(captured.panes['Drawdown from peak']?.hiddenSeries?.has('fund')).toBe(true);
    } finally {
      await act(async () => root.unmount());
      host.remove();
    }
  });
});
