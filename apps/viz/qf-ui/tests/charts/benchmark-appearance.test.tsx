/**
 * One source of truth for benchmark appearance.
 *
 * USAGE:
 *   pnpm test -- tests/charts/benchmark-appearance.test.tsx
 */

// --------------------------------------------------------------------------- #
// Mocks
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const overlayColors = vi.hoisted<string[]>(() => []);

vi.mock('../../src/charts/components/MultiSeriesPlotHost', () => ({
  MultiSeriesPlotHost: ({ overlayColor }: { overlayColor: string }) => {
    overlayColors.push(overlayColor);
    return <div data-testid="plot-host" />;
  },
}));

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { MultiSeriesTimeChart } from '../../src/charts/charts/MultiSeriesTimeChart';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const SERIES = [
  {
    metric: 'pnl',
    axis: 'left' as const,
    label: 'PnL',
    points: [
      { x: new Date('2026-01-01T00:00:00Z'), y: 1 },
      { x: new Date('2026-01-02T00:00:00Z'), y: 2 },
    ],
  },
];

const BENCHMARK = {
  id: 'btc',
  label: 'BTC',
  points: [
    { date: new Date('2026-01-01T00:00:00Z'), value: 10 },
    { date: new Date('2026-01-02T00:00:00Z'), value: 12 },
  ],
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('benchmark appearance', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    overlayColors.length = 0;
    document.documentElement.style.setProperty('--qf-chart-benchmark', '11 22% 33%');
    window.dispatchEvent(new Event('qf:chart-theme-change'));
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => {
    document.documentElement.style.removeProperty('--qf-chart-benchmark');
    window.dispatchEvent(new Event('qf:chart-theme-change'));
    host.remove();
  });

  it('takes the tooltip swatch from the semantic theme, not a second literal', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<MultiSeriesTimeChart series={SERIES} benchmark={BENCHMARK} />),
    );

    expect(overlayColors.at(-1)).toBe('hsl(11 22% 33%)');
    await act(async () => root.unmount());
  });

  it('passes a full host colour through unchanged', async () => {
    document.documentElement.style.setProperty('--qf-chart-benchmark', 'oklch(0.72 0.005 90)');
    window.dispatchEvent(new Event('qf:chart-theme-change'));
    const root = createRoot(host);
    await act(async () =>
      root.render(<MultiSeriesTimeChart series={SERIES} benchmark={BENCHMARK} />),
    );

    expect(overlayColors.at(-1)).toBe('oklch(0.72 0.005 90)');
    await act(async () => root.unmount());
  });
});
