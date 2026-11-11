/**
 * Line-chart area-gradient option contract.
 *
 * USAGE:
 *   pnpm test -- tests/charts/line-chart-area-gradient.test.tsx
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

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LineChart area gradients', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('passes a horizontal hard-stop gradient to one ECharts area series', async () => {
    const series: readonly QfLineSeries[] = [
      {
        key: 'regimes',
        label: 'Regimes',
        points: [
          { date: new Date('2026-01-01T00:00:00Z'), value: 1 },
          { date: new Date('2026-01-02T00:00:00Z'), value: 2 },
        ],
        area: true,
        areaColor: {
          stops: [
            { offset: 0, color: 'rgb(0, 0, 255)' },
            { offset: 0.5, color: 'rgb(0, 0, 255)' },
            { offset: 0.5, color: 'rgb(255, 0, 0)' },
            { offset: 1, color: 'rgb(255, 0, 0)' },
          ],
        },
      },
    ];
    const root = createRoot(host);
    await act(async () => root.render(<LineChart series={series} height={320} />));
    const option = capturedOptions.at(-1) as {
      series: Array<{ areaStyle: { color: unknown } }>;
    };

    expect(option.series).toHaveLength(1);
    expect(option.series[0]?.areaStyle.color).toEqual({
      type: 'linear',
      x: 0,
      y: 0,
      x2: 1,
      y2: 0,
      colorStops: [
        { offset: 0, color: 'rgb(0, 0, 255)' },
        { offset: 0.5, color: 'rgb(0, 0, 255)' },
        { offset: 0.5, color: 'rgb(255, 0, 0)' },
        { offset: 1, color: 'rgb(255, 0, 0)' },
      ],
      global: false,
    });

    await act(async () => root.unmount());
  });
});
