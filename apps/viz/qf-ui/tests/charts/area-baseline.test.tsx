/**
 * Area-baseline forwarding from the segmented builder through to ECharts.
 *
 * USAGE:
 *   pnpm test -- tests/charts/area-baseline.test.tsx
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
import { buildSegmentedAreaSeries } from '../../src/charts/charts/segmentedAreaSeries';
import { TimeSeriesPlot } from '../../src/charts/charts/TimeSeriesPlot';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const POINTS = [
  { date: new Date('2026-01-01T00:00:00Z'), value: 3 },
  { date: new Date('2026-01-02T00:00:00Z'), value: 5 },
];

function lastAreaOrigin(): unknown {
  const option = capturedOptions.at(-1) as {
    series: Array<{ areaStyle?: { origin?: unknown } }>;
  };
  return option.series[0]?.areaStyle?.origin;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('area baseline', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('fills an all-positive zero-baseline series from zero, not the axis edge', async () => {
    const series: readonly QfLineSeries[] = [
      { key: 'a', label: 'A', points: POINTS, area: true, areaBaseline: 'zero' },
    ];
    const root = createRoot(host);
    await act(async () => root.render(<LineChart series={series} height={320} />));

    expect(lastAreaOrigin()).toBe(0);
    await act(async () => root.unmount());
  });

  it('leaves a range-baseline series on the engine default', async () => {
    const series: readonly QfLineSeries[] = [
      { key: 'a', label: 'A', points: POINTS, area: true, areaBaseline: 'range' },
    ];
    const root = createRoot(host);
    await act(async () => root.render(<LineChart series={series} height={320} />));

    expect(lastAreaOrigin()).toBe('auto');
    await act(async () => root.unmount());
  });

  it('forwards the baseline the segmented-area builder sets through TimeSeriesPlot', async () => {
    const built = buildSegmentedAreaSeries({
      points: [
        { date: POINTS[0]?.date ?? new Date(), value: 3, segment: 'a' },
        { date: POINTS[1]?.date ?? new Date(), value: 5, segment: 'a' },
      ],
      segments: [{ id: 'a', color: 'rgb(0, 0, 255)' }],
    });
    expect(built[0]?.areaBaseline).toBe('zero');

    const root = createRoot(host);
    await act(async () =>
      root.render(
        <TimeSeriesPlot
          data={built[0]?.data ?? []}
          series={built}
          xDomain={[POINTS[0]?.date ?? new Date(), POINTS[1]?.date ?? new Date()]}
        />,
      ),
    );

    expect(lastAreaOrigin()).toBe(0);
    await act(async () => root.unmount());
  });
});
