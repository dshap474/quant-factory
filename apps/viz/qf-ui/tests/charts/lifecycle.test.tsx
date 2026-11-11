/**
 * ECharts registration, resize, disposal, and Strict Mode lifecycle tests.
 *
 * USAGE:
 *   pnpm test -- lifecycle.test.tsx
 */

// --------------------------------------------------------------------------- #
// Mocks
// --------------------------------------------------------------------------- #

import { act, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const runtime = vi.hoisted(() => {
  let failNextSetOption = false;
  const instances: Array<{
    dispose: ReturnType<typeof vi.fn>;
    isDisposed: ReturnType<typeof vi.fn>;
    off: ReturnType<typeof vi.fn>;
    on: ReturnType<typeof vi.fn>;
    resize: ReturnType<typeof vi.fn>;
    setOption: ReturnType<typeof vi.fn>;
  }> = [];
  const use = vi.fn();
  const init = vi.fn(() => {
    let disposed = false;
    const instance = {
      dispose: vi.fn(() => {
        disposed = true;
      }),
      isDisposed: vi.fn(() => disposed),
      off: vi.fn(),
      on: vi.fn(),
      resize: vi.fn(),
      setOption: vi.fn(() => {
        if (!failNextSetOption) return;
        failNextSetOption = false;
        throw new Error('invalid option');
      }),
    };
    instances.push(instance);
    return instance;
  });
  return {
    init,
    instances,
    use,
    failNextSetOption: () => {
      failNextSetOption = true;
    },
  };
});

vi.mock('echarts/core', () => ({ init: runtime.init, use: runtime.use }));

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QfChart } from '../../src/charts/core/QfChart';
import { registerCharts } from '../../src/charts/core/registerCharts';
import { TestResizeObserver } from '../setup-charts';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('QfChart lifecycle', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    runtime.instances.length = 0;
    TestResizeObserver.instances.length = 0;
  });

  afterEach(() => {
    host.remove();
  });

  it('registers the tree-shaken runtime idempotently', () => {
    const initialCalls = runtime.use.mock.calls.length;
    registerCharts();
    registerCharts();
    expect(runtime.use).toHaveBeenCalledTimes(initialCalls);
  });

  it('resizes and disposes one mounted instance exactly once', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const instance = runtime.instances[0];
    const observer = TestResizeObserver.instances[0];
    expect(instance).toBeDefined();
    expect(observer).toBeDefined();
    if (!instance || !observer) throw new Error('chart lifecycle was not initialized');
    await act(async () =>
      observer.callback([{ contentRect: { width: 320 } } as ResizeObserverEntry], observer),
    );
    expect(instance.resize).toHaveBeenCalledTimes(1);
    await act(async () => root.unmount());
    expect(instance.dispose).toHaveBeenCalledTimes(1);
  });

  it('does not leak instances or listeners under Strict Mode', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <StrictMode>
          <QfChart option={{ series: [] }} ariaLabel="Chart" />
        </StrictMode>,
      ),
    );
    await act(async () => root.unmount());
    expect(runtime.instances).toHaveLength(2);
    for (const instance of runtime.instances) {
      expect(instance.on).toHaveBeenCalledTimes(1);
      expect(instance.off).toHaveBeenCalledTimes(1);
      expect(instance.dispose).toHaveBeenCalledTimes(1);
    }
  });

  it('shows a recoverable error and retries the current option', async () => {
    runtime.failNextSetOption();
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const instance = runtime.instances[0];
    expect(host.querySelector('[role="alert"]')?.textContent).toContain('Chart failed to update');
    const retry = host.querySelector<HTMLButtonElement>('button');
    if (!retry || !instance) throw new Error('recoverable chart error did not render');
    await act(async () => retry.click());
    expect(instance.setOption).toHaveBeenCalledTimes(2);
    expect(host.querySelector('[role="alert"]')).toBeNull();
    await act(async () => root.unmount());
  });

  it('applies the current option to a recreated instance after retry', async () => {
    runtime.failNextSetOption();
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const first = runtime.instances[0];
    const retry = host.querySelector<HTMLButtonElement>('button');
    if (!first || !retry) throw new Error('recoverable chart error did not render');
    first.isDisposed.mockReturnValue(true);
    await act(async () => retry.click());
    const second = runtime.instances[1];
    expect(second).toBeDefined();
    if (!second) throw new Error('retry did not recreate the chart instance');
    expect(second.setOption).toHaveBeenCalledTimes(1);
    expect(host.querySelector('[role="alert"]')).toBeNull();
    await act(async () => root.unmount());
  });

  it('keeps the accessible name on a wrapper that ECharts never owns', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<QfChart option={{ series: [] }} ariaLabel="Equity curve" interactive />),
    );
    const wrapper = host.querySelector<HTMLElement>('.qf-chart');
    const canvasHost = host.querySelector<HTMLElement>('.qf-chart-canvas');
    if (!wrapper || !canvasHost) throw new Error('chart wrapper shape did not render');

    expect(wrapper.getAttribute('role')).toBe('button');
    expect(wrapper.getAttribute('aria-label')).toBe('Equity curve');
    expect(canvasHost.getAttribute('aria-hidden')).toBe('true');
    expect(canvasHost.parentElement).toBe(wrapper);
    expect(runtime.init).toHaveBeenLastCalledWith(canvasHost, undefined, expect.anything());
    await act(async () => root.unmount());
  });

  it('renders the error overlay as a sibling of the ECharts child inside the wrapper', async () => {
    runtime.failNextSetOption();
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const wrapper = host.querySelector<HTMLElement>('.qf-chart');
    const overlay = host.querySelector<HTMLElement>('.qf-chart-error');
    const canvasHost = host.querySelector<HTMLElement>('.qf-chart-canvas');
    if (!wrapper || !overlay || !canvasHost) throw new Error('error overlay did not render');

    expect(overlay.parentElement).toBe(wrapper);
    expect(canvasHost.parentElement).toBe(wrapper);
    expect(overlay.previousElementSibling).toBe(canvasHost);
    await act(async () => root.unmount());
  });

  it('observes the ECharts child so resize geometry is unchanged', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const observer = TestResizeObserver.instances[0];
    const canvasHost = host.querySelector<HTMLElement>('.qf-chart-canvas');
    if (!observer || !canvasHost) throw new Error('resize observation did not initialize');

    expect(observer.target).toBe(canvasHost);
    await act(async () => root.unmount());
  });

  it('merges an option update that keeps the same structure so user zoom survives', async () => {
    const base = {
      series: [{ id: 'a', type: 'line', data: [1, 2] }],
      xAxis: {},
      yAxis: [{}],
      dataZoom: [{ type: 'inside' }],
    };
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={base} ariaLabel="Chart" />));
    const instance = runtime.instances[0];
    if (!instance) throw new Error('chart did not initialize');
    expect(instance.setOption).toHaveBeenLastCalledWith(expect.anything(), { notMerge: true });

    await act(async () =>
      root.render(
        <QfChart
          option={{ ...base, series: [{ id: 'a', type: 'line', data: [3, 4] }] }}
          ariaLabel="Chart"
        />,
      ),
    );
    expect(instance.setOption).toHaveBeenLastCalledWith(expect.anything(), { notMerge: false });
    await act(async () => root.unmount());
  });

  it('replaces the option when the structure changes so stale series cannot survive', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <QfChart
          option={{
            series: [
              { id: 'a', type: 'line', data: [] },
              { id: 'b', type: 'line', data: [] },
            ],
            yAxis: [{}],
          }}
          ariaLabel="Chart"
        />,
      ),
    );
    const instance = runtime.instances[0];
    if (!instance) throw new Error('chart did not initialize');

    await act(async () =>
      root.render(
        <QfChart
          option={{ series: [{ id: 'a', type: 'line', data: [] }], yAxis: [{}] }}
          ariaLabel="Chart"
        />,
      ),
    );
    expect(instance.setOption).toHaveBeenLastCalledWith(expect.anything(), { notMerge: true });
    await act(async () => root.unmount());
  });

  it('replaces options on first paint and merges them when interaction state is preserved', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<QfChart option={{ series: [] }} ariaLabel="Chart" />));
    const first = runtime.instances[0];
    if (!first) throw new Error('chart did not initialize');
    expect(first.setOption).toHaveBeenLastCalledWith(expect.anything(), { notMerge: true });
    await act(async () => root.unmount());

    const second = createRoot(host);
    await act(async () =>
      second.render(<QfChart option={{ series: [] }} ariaLabel="Chart" preserveInteractionState />),
    );
    const instance = runtime.instances[1];
    if (!instance) throw new Error('chart did not reinitialize');
    expect(instance.setOption).toHaveBeenLastCalledWith(expect.anything(), { notMerge: false });
    await act(async () => second.unmount());
  });
});
