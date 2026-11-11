/**
 * Chart interaction and responsive geometry contract tests.
 *
 * USAGE:
 *   pnpm test -- interactions.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MultiSeriesTimeChart } from '../../src/charts/charts';
import type { ChartTransformState } from '../../src/charts/charts/timeSeriesTransforms';
import { BrushBar, ChartLegendLabel } from '../../src/charts/components';
import { useChartBrush, useChartTransformGroup, useResponsiveChart } from '../../src/charts/hooks';
import { TestResizeObserver } from '../setup-charts';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const points = Array.from({ length: 7 }, (_, index) => ({
  date: new Date(Date.UTC(2026, 0, index + 1)),
  value: index,
}));

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('controlled chart interactions', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    TestResizeObserver.instances.length = 0;
  });

  afterEach(() => host.remove());

  it('preserves the full domain while controlled brush ranges change', async () => {
    let brush: ReturnType<typeof useChartBrush<(typeof points)[number]>> | undefined;
    function Probe() {
      brush = useChartBrush(points);
      return null;
    }
    const root = createRoot(host);
    await act(async () => root.render(<Probe />));
    expect(brush?.fullDomain).toEqual([points[0]?.date, points.at(-1)?.date]);
    await act(async () =>
      brush?.setDomain([points[2]?.date ?? new Date(), points[3]?.date ?? new Date()]),
    );
    expect(brush?.fullDomain).toEqual([points[0]?.date, points.at(-1)?.date]);
    expect(brush?.visibleData.map((point) => point.value)).toEqual([1, 2, 3, 4]);
    await act(async () => root.unmount());
  });

  it('emits controlled brush updates without exposing Reset', async () => {
    const changes: Array<readonly [Date, Date] | undefined> = [];
    const root = createRoot(host);
    await act(async () =>
      root.render(<BrushBar data={points} onDomainChange={(domain) => changes.push(domain)} />),
    );
    const end = host.querySelector<HTMLInputElement>('[aria-label="Brush end"]');
    expect(end).not.toBeNull();
    if (!end) throw new Error('brush end input was not rendered');
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setValue?.call(end, '80');
      end.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(host.textContent).not.toMatch(/Reset/i);
    expect(host.querySelectorAll('input[type="range"]')).toHaveLength(2);
    expect(changes).toHaveLength(1);
    expect(changes[0]?.[1]).toEqual(new Date(Date.UTC(2026, 0, 5, 19, 12)));
  });

  it('reflects controlled transform state and emits toolbar changes', async () => {
    const changes: ChartTransformState[] = [];
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiSeriesTimeChart
          series={[
            {
              metric: 'metric',
              axis: 'left',
              label: 'Metric',
              points: points.map((point) => ({ x: point.date, y: point.value })),
            },
          ]}
          transformControls={{ zScore: true, ema: true }}
          transformState={{ zScore: 90, ema: null }}
          onTransformStateChange={(value) => changes.push(value)}
        />,
      ),
    );
    const z30 = host.querySelector<HTMLButtonElement>('[aria-label="30-day trailing Z-score"]');
    const z90 = host.querySelector<HTMLButtonElement>('[aria-label="90-day trailing Z-score"]');
    if (!z30 || !z90) throw new Error('controlled transform toolbar did not render');
    expect(z90.ariaPressed).toBe('true');
    await act(async () => z30.click());
    expect(changes).toEqual([{ zScore: 30, ema: null }]);
    expect(z90.ariaPressed).toBe('true');
    await act(async () => root.unmount());
  });

  it('excludes benchmark series from the legend while retaining comparison controls', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiSeriesTimeChart
          series={[
            {
              metric: 'strategy',
              axis: 'left',
              label: 'Current',
              points: points.map((point) => ({ x: point.date, y: point.value })),
            },
            {
              metric: 'control',
              axis: 'left',
              label: 'Comparison',
              points: points.map((point) => ({ x: point.date, y: point.value })),
            },
            {
              metric: 'btc',
              axis: 'left',
              label: 'BTC',
              isBenchmark: true,
              points: points.map((point) => ({ x: point.date, y: point.value })),
            },
          ]}
        />,
      ),
    );
    expect(host.querySelector('[aria-label="Hide BTC"]')).toBeNull();
    expect(host.querySelector('[aria-label="Show BTC"]')).toBeNull();
    expect(host.querySelector('[aria-label="Hide Comparison"]')?.getAttribute('aria-pressed')).toBe(
      'true',
    );
    await act(async () => root.unmount());
  });

  it('excludes a dedicated price overlay from the legend', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <MultiSeriesTimeChart
          series={[
            {
              metric: 'metric',
              axis: 'left',
              label: 'Metric',
              points: points.map((point) => ({ x: point.date, y: point.value })),
            },
          ]}
          benchmark={{
            id: 'btc',
            label: 'BTC',
            points: points.map((point) => ({ date: point.date, value: point.value + 1 })),
          }}
        />,
      ),
    );
    expect(host.querySelector('[aria-label="Hide BTC overlay"]')).toBeNull();
    expect(host.querySelector('[aria-label="Show BTC overlay"]')).toBeNull();
    expect(host.querySelector('[aria-label="Hide Metric"]')).not.toBeNull();
    await act(async () => root.unmount());
  });

  it('coordinates a master transform baseline with per-chart overrides', async () => {
    let transforms: ReturnType<typeof useChartTransformGroup> | undefined;
    function Probe() {
      transforms = useChartTransformGroup();
      return null;
    }
    const root = createRoot(host);
    await act(async () => root.render(<Probe />));

    await act(async () => transforms?.applyMasterState({ zScore: 90, ema: null }));
    expect(transforms?.stateFor('volume')).toEqual({ zScore: 90, ema: null });
    expect(transforms?.stateFor('funding')).toEqual({ zScore: 90, ema: null });

    await act(async () => transforms?.updateChartState('volume', { zScore: 30, ema: null }));
    expect(transforms?.stateFor('volume')).toEqual({ zScore: 30, ema: null });
    expect(transforms?.stateFor('funding')).toEqual({ zScore: 90, ema: null });

    await act(async () => transforms?.applyMasterState({ zScore: 180, ema: 30 }));
    expect(transforms?.stateFor('volume')).toEqual({ zScore: 180, ema: 30 });
    await act(async () => root.unmount());
  });

  it('latches pointer drags to one domain update per animation frame', async () => {
    const frames: FrameRequestCallback[] = [];
    const originalRaf = window.requestAnimationFrame;
    const originalCancel = window.cancelAnimationFrame;
    Object.defineProperty(window, 'requestAnimationFrame', {
      configurable: true,
      value: (callback: FrameRequestCallback) => frames.push(callback),
    });
    Object.defineProperty(window, 'cancelAnimationFrame', {
      configurable: true,
      value: () => undefined,
    });
    Object.defineProperty(Element.prototype, 'setPointerCapture', {
      configurable: true,
      value: () => undefined,
    });
    Object.defineProperty(Element.prototype, 'hasPointerCapture', {
      configurable: true,
      value: () => false,
    });
    try {
      const changes: Array<readonly [Date, Date] | undefined> = [];
      const root = createRoot(host);
      await act(async () =>
        root.render(<BrushBar data={points} onDomainChange={(domain) => changes.push(domain)} />),
      );
      const edge = host.querySelector('.qf-brush-edge-end');
      if (!edge) throw new Error('brush end edge was not rendered');
      // The jsdom track rect is zero-width, so pointerPercent maps clientX 1:100.
      const pointer = (type: string, clientX: number) => {
        const event = new Event(type, { bubbles: true }) as Event & {
          clientX: number;
          pointerId: number;
        };
        event.clientX = clientX;
        event.pointerId = 1;
        return event;
      };
      await act(async () => edge.dispatchEvent(pointer('pointerdown', 0)));
      await act(async () => {
        edge.dispatchEvent(pointer('pointermove', -0.1));
        edge.dispatchEvent(pointer('pointermove', -0.2));
      });
      expect(changes).toHaveLength(0);
      expect(frames).toHaveLength(1);
      await act(async () => frames[0]?.(0));
      expect(changes).toHaveLength(1);
      expect(changes[0]?.[1]).toEqual(new Date(Date.UTC(2026, 0, 5, 19, 12)));
      await act(async () => {
        edge.dispatchEvent(pointer('pointermove', -0.3));
        edge.dispatchEvent(pointer('pointerup', -0.3));
      });
      expect(changes).toHaveLength(2);
      expect(changes[1]?.[1]).toEqual(new Date(Date.UTC(2026, 0, 5, 4, 48)));
      await act(async () => root.unmount());
    } finally {
      Object.defineProperty(window, 'requestAnimationFrame', {
        configurable: true,
        value: originalRaf,
      });
      Object.defineProperty(window, 'cancelAnimationFrame', {
        configurable: true,
        value: originalCancel,
      });
    }
  });

  it('clamps responsive geometry to valid narrow dimensions', async () => {
    let result: ReturnType<typeof useResponsiveChart> | undefined;
    function Probe() {
      result = useResponsiveChart({ aspectRatio: 16 / 9, minWidth: 120, minHeight: 80 });
      return <div ref={result.ref} />;
    }
    const root = createRoot(host);
    await act(async () => root.render(<Probe />));
    const observer = TestResizeObserver.instances[0];
    if (!observer) throw new Error('responsive observer was not created');
    await act(async () =>
      observer.callback([{ contentRect: { width: 80 } } as ResizeObserverEntry], observer),
    );
    expect(result).toMatchObject({ width: 120, height: 80 });
    await act(async () => root.unmount());
  });

  it('reveals full legend text on hover only when the visible label is truncated', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<ChartLegendLabel>Series A versus series B</ChartLegendLabel>),
    );
    const wrapper = host.querySelector<HTMLElement>('.chart-legend-label-wrap');
    const label = host.querySelector<HTMLElement>('.chart-legend-label');
    const observer = TestResizeObserver.instances[0];
    if (!wrapper || !label || !observer) throw new Error('legend label did not render');

    Object.defineProperties(label, {
      clientWidth: { configurable: true, value: 64 },
      scrollWidth: { configurable: true, value: 180 },
    });
    await act(async () => observer.callback([], observer));
    await act(async () => wrapper.dispatchEvent(new Event('pointerover', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe(
      'Series A versus series B',
    );

    await act(async () => wrapper.dispatchEvent(new Event('pointerout', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();

    Object.defineProperty(label, 'scrollWidth', { configurable: true, value: 64 });
    await act(async () => observer.callback([], observer));
    await act(async () => wrapper.dispatchEvent(new Event('pointerover', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();
    await act(async () => root.unmount());
  });

  it('makes truncated legend text keyboard-discoverable and dismisses it with Escape', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<ChartLegendLabel>Series A versus series B</ChartLegendLabel>),
    );
    const wrapper = host.querySelector<HTMLElement>('.chart-legend-label-wrap');
    const label = host.querySelector<HTMLElement>('.chart-legend-label');
    const observer = TestResizeObserver.instances[0];
    if (!wrapper || !label || !observer) throw new Error('legend label did not render');

    Object.defineProperties(label, {
      clientWidth: { configurable: true, value: 64 },
      scrollWidth: { configurable: true, value: 180 },
    });
    await act(async () => observer.callback([], observer));

    expect(wrapper.tabIndex).toBe(0);
    await act(async () => wrapper.focus());
    const tooltip = document.body.querySelector<HTMLElement>('[role="tooltip"]');
    expect(tooltip?.textContent).toBe('Series A versus series B');
    expect(wrapper.getAttribute('aria-describedby')).toBe(tooltip?.id);

    await act(async () =>
      wrapper.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
      ),
    );
    expect(document.activeElement).toBe(wrapper);
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();
    expect(wrapper.getAttribute('aria-describedby')).toBeNull();
    await act(async () => root.unmount());
  });
});
