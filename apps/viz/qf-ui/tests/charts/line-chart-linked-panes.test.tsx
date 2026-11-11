/**
 * Line-chart geometry inside a linked multi-pane stack, plus background bands.
 *
 * USAGE:
 *   pnpm test -- line-chart-linked-panes.test.tsx
 */

// --------------------------------------------------------------------------- #
// Mocks
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const capturedOptions = vi.hoisted<Array<Record<string, unknown>>>(() => []);

vi.mock(import('../../src/charts/core/QfChart'), async (importOriginal) => ({
  ...(await importOriginal()),
  QfChart: ({ option }: { option: Record<string, unknown> }) => {
    capturedOptions.push(option);
    return <div data-testid="qf-chart" />;
  },
}));

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { LineChart, type QfLineSeries, type QfXBand } from '../../src/charts/charts/LineChart';
import { formatTooltipDate } from '../../src/charts/charts/timeAxisFormat';
import {
  type MultiPaneLink,
  MultiPaneLinkProvider,
} from '../../src/charts/components/MultiPaneContext';
import { MultiPaneTimeSeriesChart } from '../../src/charts/components/MultiPaneTimeSeriesChart';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const series: readonly QfLineSeries[] = [
  {
    key: 'score',
    label: 'Score',
    points: [
      { date: new Date('2026-01-01T00:00:00Z'), value: 1 },
      { date: new Date('2026-01-02T00:00:00Z'), value: 2 },
    ],
  },
];
const domain: readonly [Date, Date] = [
  new Date('2025-12-01T00:00:00Z'),
  new Date('2026-02-01T00:00:00Z'),
];

interface CapturedOption {
  grid: { top: number; right: number; bottom: number; left: number; containLabel: boolean };
  tooltip: { show?: boolean; axisPointer?: { type: string } };
  xAxis: {
    min?: number;
    max?: number;
    axisLabel: { show: boolean };
    axisLine: { show: boolean };
    axisPointer: { show: boolean; type: string; label: { show: boolean } };
  };
  yAxis: Array<{
    splitNumber?: number;
    axisLabel: { showMinLabel?: boolean; showMaxLabel?: boolean };
    axisLine: { show: boolean };
  }>;
  series: Array<{ markArea?: { data: unknown[] } }>;
}

function movePointer(target: Element, x: number, y: number, width = 400, height = 300) {
  Object.defineProperty(target, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({ left: 0, top: 0, width, height, right: width, bottom: height }),
  });
  target.dispatchEvent(
    new PointerEvent('pointermove', {
      clientX: x,
      clientY: y,
      bubbles: true,
      pointerType: 'mouse',
    }),
  );
}

function renderLinked(link: MultiPaneLink, chart = <LineChart series={series} height="100%" />) {
  return <MultiPaneLinkProvider value={link}>{chart}</MultiPaneLinkProvider>;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LineChart inside a linked pane', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('uses the shared gutters, hides the time axis above the bottom pane, and takes the stack domain', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        renderLinked({ position: 'top', gutter: { left: 64, right: 16 }, xDomain: domain }),
      ),
    );
    const top = capturedOptions.at(-1) as unknown as CapturedOption;
    expect(top.grid).toMatchObject({
      top: 32,
      right: 16,
      bottom: 12,
      left: 64,
      containLabel: false,
    });
    expect(top.xAxis.axisLabel.show).toBe(false);
    expect(top.xAxis.axisLine.show).toBe(false);
    expect(top.xAxis.axisPointer).toMatchObject({ show: true, type: 'none' });
    expect(top.xAxis.min).toBe(domain[0].getTime());
    expect(top.xAxis.max).toBe(domain[1].getTime());
    expect(top.yAxis[0]?.splitNumber).toBe(3);
    expect(top.yAxis[0]?.axisLine.show).toBe(false);
    expect(top.yAxis[0]?.axisLabel).not.toHaveProperty('showMinLabel');
    expect(top.tooltip.axisPointer?.type).toBe('none');

    await act(async () =>
      root.render(
        renderLinked({ position: 'bottom', gutter: { left: 64, right: 16 }, xDomain: domain }),
      ),
    );
    const bottom = capturedOptions.at(-1) as unknown as CapturedOption;
    expect(bottom.grid).toMatchObject({ top: 32, bottom: 26, left: 64 });
    expect(bottom.xAxis.axisLabel.show).toBe(true);
    expect(bottom.xAxis.axisLine.show).toBe(true);

    await act(async () => root.unmount());
  });

  it('lets an explicit chart domain and tick count override the stack defaults', async () => {
    const root = createRoot(host);
    const own: readonly [Date, Date] = [
      new Date('2026-01-01T00:00:00Z'),
      new Date('2026-01-02T00:00:00Z'),
    ];
    await act(async () =>
      root.render(
        renderLinked(
          { position: 'only', gutter: { left: 48, right: 8 }, xDomain: domain },
          <LineChart series={series} height="100%" xDomain={own} ySplitNumber={5} />,
        ),
      ),
    );
    const option = capturedOptions.at(-1) as unknown as CapturedOption;
    expect(option.grid).toMatchObject({ left: 48, right: 8, bottom: 26 });
    expect(option.xAxis.min).toBe(own[0].getTime());
    expect(option.yAxis[0]?.splitNumber).toBe(5);

    await act(async () => root.unmount());
  });

  it('keeps the standalone geometry when no stack links the chart', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<LineChart series={series} height={320} />));
    const option = capturedOptions.at(-1) as unknown as CapturedOption;
    expect(option.grid).toMatchObject({
      top: 16,
      right: 16,
      bottom: 16,
      left: 16,
      containLabel: true,
    });
    expect(option.xAxis.axisLabel.show).toBe(true);
    expect(option.xAxis.axisPointer).toMatchObject({
      show: true,
      type: 'line',
      label: { show: false },
    });
    expect(option.yAxis[0]?.splitNumber).toBeUndefined();
    expect(option.yAxis[0]?.axisLabel.showMinLabel).toBeUndefined();

    await act(async () => root.unmount());
  });
});

describe('LineChart background bands', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('draws each band as a silent mark area on the first plotted series', async () => {
    const root = createRoot(host);
    const bands: readonly QfXBand[] = [
      { from: domain[0], to: domain[1], color: '#123456' },
      { from: domain[1], to: new Date('2026-03-01T00:00:00Z'), color: '#654321', opacity: 0.2 },
    ];
    await act(async () => root.render(<LineChart series={series} height={320} xBands={bands} />));
    const option = capturedOptions.at(-1) as unknown as CapturedOption;
    expect(option.series[0]?.markArea).toMatchObject({
      silent: true,
      data: [
        [
          { xAxis: domain[0].getTime(), itemStyle: { color: 'rgb(18, 52, 86)', opacity: 0.08 } },
          { xAxis: domain[1].getTime() },
        ],
        [{ itemStyle: { color: 'rgb(101, 67, 33)', opacity: 0.2 } }, {}],
      ],
    });

    await act(async () => root.render(<LineChart series={series} height={320} />));
    expect(
      (capturedOptions.at(-1) as unknown as CapturedOption).series[0]?.markArea,
    ).toBeUndefined();

    await act(async () => root.unmount());
  });
});

describe('MultiPaneTimeSeriesChart linked mode', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    capturedOptions.length = 0;
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('links every pane with its position and the shared domain', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          linked
          xDomain={domain}
          panes={[
            { id: 'a', label: 'A', content: <LineChart series={series} height="100%" /> },
            { id: 'b', label: 'B', content: <LineChart series={series} height="100%" /> },
            { id: 'c', label: 'C', content: <LineChart series={series} height="100%" /> },
          ]}
        />,
      ),
    );
    const options = capturedOptions.slice(-3) as unknown as CapturedOption[];
    expect(options.map((option) => option.xAxis.axisLabel.show)).toEqual([false, false, true]);
    expect(options.map((option) => option.grid.bottom)).toEqual([12, 12, 26]);
    expect(options.every((option) => option.xAxis.min === domain[0].getTime())).toBe(true);
    expect(host.querySelectorAll('.qf-multi-pane-chart-pane.is-linked')).toHaveLength(3);
    expect(host.querySelector('.qf-multi-pane-chart-stack.is-linked')).not.toBeNull();

    await act(async () => root.unmount());
  });

  it('leaves unlinked stacks on the standalone per-pane geometry', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          panes={[
            { id: 'a', label: 'A', content: <LineChart series={series} height="100%" /> },
            { id: 'b', label: 'B', content: <LineChart series={series} height="100%" /> },
          ]}
        />,
      ),
    );
    const options = capturedOptions.slice(-2) as unknown as CapturedOption[];
    expect(options.map((option) => option.xAxis.axisLabel.show)).toEqual([true, true]);
    expect(options.every((option) => option.grid.containLabel)).toBe(true);
    expect(host.querySelector('.qf-multi-pane-chart-pane.is-linked')).toBeNull();

    await act(async () => root.unmount());
  });

  it('sizes one shared gutter from the widest value labels any pane reports', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          linked
          xDomain={domain}
          panes={[
            {
              id: 'price',
              label: 'Price',
              content: (
                <LineChart
                  series={series}
                  height="100%"
                  yDomain={[80_000, 120_000]}
                  yFormat={(value) => `$${(value / 1_000).toFixed(1)}k`}
                />
              ),
            },
            {
              id: 'score',
              label: 'Score',
              content: (
                <LineChart
                  series={series}
                  height="100%"
                  yDomain={[0, 1]}
                  yFormat={(value) => value.toFixed(1)}
                />
              ),
            },
          ]}
        />,
      ),
    );
    // Card inset, seven-character price labels at the 12px fallback glyph width, label gap.
    const expectedLeft = 16 + Math.ceil(7 * 12 * 0.6) + 8;
    const options = capturedOptions.slice(-2) as unknown as CapturedOption[];
    expect(options.map((option) => option.grid.left)).toEqual([expectedLeft, expectedLeft]);
    const labels = host.querySelectorAll<HTMLElement>('.qf-multi-pane-chart-pane-label');
    expect([...labels].map((label) => label.style.left)).toEqual([
      `${expectedLeft}px`,
      `${expectedLeft}px`,
    ]);

    await act(async () => root.unmount());
  });

  it('keeps an explicit left gutter over the measured one', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          linked
          xDomain={domain}
          gutter={{ left: 96 }}
          panes={[
            {
              id: 'price',
              label: 'Price',
              content: <LineChart series={series} height="100%" yDomain={[80_000, 120_000]} />,
            },
          ]}
        />,
      ),
    );
    expect((capturedOptions.at(-1) as unknown as CapturedOption).grid.left).toBe(96);

    await act(async () => root.unmount());
  });

  it('renders one tooltip for every pane that declares rows and silences the pane tooltips', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          linked
          xDomain={domain}
          gutter={{ left: 64, right: 16 }}
          panes={[
            {
              id: 'price',
              label: 'Price',
              content: <LineChart series={series} height="100%" />,
              tooltip: (date) => ({
                date,
                items: [{ label: 'BTC', value: `$${date.getUTCDate()}` }],
              }),
            },
            {
              id: 'score',
              label: 'Score',
              content: <LineChart series={series} height="100%" />,
              tooltip: (date) => ({ date, items: [{ label: 'Score', value: '0.50' }] }),
            },
            {
              id: 'silent',
              label: 'Silent',
              content: <LineChart series={series} height="100%" />,
              tooltip: () => null,
            },
          ]}
        />,
      ),
    );
    const options = capturedOptions.slice(-3) as unknown as CapturedOption[];
    expect(options.map((option) => option.tooltip.show)).toEqual([false, false, false]);
    // No pane pointer either: the stack's crosshair is the only cursor feedback.
    expect(options.map((option) => option.xAxis.axisPointer.show)).toEqual([false, false, false]);
    expect(host.querySelector('.qf-multi-pane-chart-tooltip')).toBeNull();

    const stack = host.querySelector('.qf-multi-pane-chart-stack');
    if (!stack) throw new Error('stack missing');
    // Halfway across the plot area: 64 + (400 - 64 - 16) / 2 = 224 → the domain midpoint.
    await act(async () => movePointer(stack, 224, 40));
    const tooltip = host.querySelector('.qf-multi-pane-chart-tooltip');
    expect(tooltip).not.toBeNull();
    expect(host.querySelector('.qf-multi-pane-chart-crosshair')).not.toBeNull();
    const midpoint = new Date((domain[0].getTime() + domain[1].getTime()) / 2);
    expect(tooltip?.querySelector('.tooltip-date')?.textContent).toBe(formatTooltipDate(midpoint));
    expect(tooltip?.querySelectorAll('.qf-multi-pane-chart-tooltip-section')).toHaveLength(2);
    expect(
      [...(tooltip?.querySelectorAll('.tooltip-row') ?? [])].map((row) => row.textContent),
    ).toEqual([`BTC$${midpoint.getUTCDate()}`, 'Score0.50']);

    // Over the left gutter there is nothing to point at.
    await act(async () => movePointer(stack, 20, 40));
    expect(host.querySelector('.qf-multi-pane-chart-tooltip')).toBeNull();
    expect(host.querySelector('.qf-multi-pane-chart-crosshair')).toBeNull();

    await act(async () => stack.dispatchEvent(new PointerEvent('pointerleave', { bubbles: true })));
    expect(host.querySelector('.qf-multi-pane-chart-tooltip')).toBeNull();

    await act(async () => root.unmount());
  });

  it('leaves the pane tooltips on when no pane declares shared rows', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiPaneTimeSeriesChart
          linked
          xDomain={domain}
          panes={[
            { id: 'a', label: 'A', content: <LineChart series={series} height="100%" /> },
            { id: 'b', label: 'B', content: <LineChart series={series} height="100%" /> },
          ]}
        />,
      ),
    );
    const options = capturedOptions.slice(-2) as unknown as CapturedOption[];
    expect(options.every((option) => option.tooltip.show !== false)).toBe(true);

    await act(async () => root.unmount());
  });
});
