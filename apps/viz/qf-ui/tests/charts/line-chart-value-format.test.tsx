/**
 * `QfSeries.valueFormat` rendering contract for the line engine.
 *
 * USAGE:
 *   pnpm test -- tests/charts/line-chart-value-format.test.tsx
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
// Fixtures
// --------------------------------------------------------------------------- #

interface CapturedOption {
  yAxis: Array<{ axisLabel: { formatter: (value: number) => string } }>;
  tooltip: { formatter?: (params: unknown) => string };
}

const POINTS = [
  { date: new Date('2026-01-01T00:00:00Z'), value: 0.0123 },
  { date: new Date('2026-01-02T00:00:00Z'), value: 0.0456 },
];

function tooltipParams(seriesId: string, value: number) {
  return [{ seriesId, seriesName: seriesId, value: [POINTS[0]?.date.getTime(), value] }];
}

async function renderChart(series: readonly QfLineSeries[], extra: Record<string, unknown> = {}) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(<LineChart series={series} height={320} {...extra} />));
  const option = capturedOptions.at(-1) as unknown as CapturedOption;
  await act(async () => root.unmount());
  host.remove();
  return option;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LineChart honours QfSeries.valueFormat', () => {
  beforeEach(() => {
    capturedOptions.length = 0;
  });

  afterEach(() => {
    capturedOptions.length = 0;
  });

  it('formats the tooltip value with the series format', async () => {
    const option = await renderChart([
      { key: 'ic', label: 'IC', valueFormat: 'percent', points: POINTS },
    ]);
    const html = option.tooltip.formatter?.(tooltipParams('ic', 0.0123)) ?? '';

    expect(html).toContain('IC');
    expect(html).toContain('1.2300%');
  });

  it('formats the value-axis labels with the series format', async () => {
    const option = await renderChart([
      { key: 'aum', label: 'AUM', valueFormat: 'currency', points: POINTS },
    ]);

    expect(option.yAxis[0]?.axisLabel.formatter(1234)).toBe('$1,234');
  });

  it('accepts a function format and applies it to the tooltip', async () => {
    const option = await renderChart([
      { key: 'raw', label: 'Raw', valueFormat: (value: number) => `${value}!`, points: POINTS },
    ]);
    const html = option.tooltip.formatter?.(tooltipParams('raw', 7)) ?? '';

    expect(html).toContain('7!');
  });

  it('lets an explicit axis formatter win over the series format', async () => {
    const option = await renderChart(
      [{ key: 'ic', label: 'IC', valueFormat: 'percent', points: POINTS }],
      { yFormat: (value: number) => `#${value}` },
    );

    expect(option.yAxis[0]?.axisLabel.formatter(3)).toBe('#3');
  });

  it('renders unformatted series as qf rows with square swatches, not ECharts markers', async () => {
    const option = await renderChart([{ key: 'plain', label: 'Plain', points: POINTS }]);
    const html = option.tooltip.formatter?.([
      {
        color: 'rgb(1, 2, 3)',
        seriesId: 'plain',
        seriesName: 'Plain',
        value: [POINTS[0]?.date.getTime(), 1234.5],
      },
    ]);

    expect(html).toContain('class="tooltip-swatch" style="--tooltip-swatch:rgb(1, 2, 3)"');
    expect(html).toContain('Plain');
    expect(html).not.toContain('border-radius:10px');
    expect(option.yAxis[0]?.axisLabel.formatter(3)).toBe('3');
  });
});
