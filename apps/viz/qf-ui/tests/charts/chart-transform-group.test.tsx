/**
 * Tests for page-wide transform coordination through ChartTransformGroupProvider.
 *
 * USAGE:
 *   pnpm exec vitest run --project charts tests/charts/chart-transform-group.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MultiSeriesTimeChart } from '../../src/charts/charts';
import type { ChartTransformControls } from '../../src/charts/charts/timeSeriesTransforms';
import {
  ChartToggleGroup,
  ChartTransformGroupProvider,
  ChartTransformMasterToolbar,
} from '../../src/charts/components';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const SERIES = [
  {
    metric: 'metric',
    axis: 'left' as const,
    label: 'Metric',
    points: Array.from({ length: 5 }, (_, index) => ({
      x: new Date(Date.UTC(2026, 0, index + 1)),
      y: index,
    })),
  },
];

function Chart({ title, controls }: { title: string; controls: ChartTransformControls }) {
  return (
    <section aria-label={title}>
      <MultiSeriesTimeChart title={title} series={SERIES} transformControls={controls} />
    </section>
  );
}

function pressed(host: HTMLElement, scope: string, label: string): string | null {
  const button = host.querySelector<HTMLButtonElement>(`${scope} [aria-label="${label}"]`);
  if (!button) throw new Error(`missing ${scope} ${label}`);
  return button.ariaPressed;
}

function click(host: HTMLElement, scope: string, label: string) {
  host.querySelector<HTMLButtonElement>(`${scope} [aria-label="${label}"]`)?.click();
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartTransformGroupProvider', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('joins member charts, unions their windows on the master, and resets overrides', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartTransformGroupProvider>
          <div id="master">
            <ChartTransformMasterToolbar />
          </div>
          <Chart title="a" controls={{ zScore: true, ema: true }} />
          <Chart title="b" controls={{ ema: [30, 90, 180, 365] }} />
        </ChartTransformGroupProvider>,
      ),
    );

    expect(host.querySelectorAll('#master button[aria-label*="trailing Z-score"]')).toHaveLength(4);
    expect(host.querySelectorAll('#master button[aria-label*="EMA smoothing"]')).toHaveLength(4);

    await act(async () => click(host, '#master', '90-day EMA smoothing'));
    expect(pressed(host, '[aria-label="a"]', '90-day EMA smoothing')).toBe('true');
    expect(pressed(host, '[aria-label="b"]', '90-day EMA smoothing')).toBe('true');

    await act(async () => click(host, '[aria-label="a"]', '30-day EMA smoothing'));
    expect(pressed(host, '[aria-label="a"]', '30-day EMA smoothing')).toBe('true');
    expect(pressed(host, '[aria-label="b"]', '90-day EMA smoothing')).toBe('true');

    await act(async () => click(host, '#master', '365-day EMA smoothing'));
    expect(pressed(host, '[aria-label="b"]', '365-day EMA smoothing')).toBe('true');
    // Chart a offers no 365-day EMA, so the master window clamps to off there.
    expect(pressed(host, '[aria-label="a"]', '30-day EMA smoothing')).toBe('false');
    expect(pressed(host, '[aria-label="a"]', '90-day EMA smoothing')).toBe('false');

    await act(async () => root.unmount());
  });
});

describe('ChartToggleGroup', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('keeps a required selection when the active option is pressed again', async () => {
    const changes: string[] = [];
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartToggleGroup
          ariaLabel="Range"
          options={[
            { value: '1y', label: '1Y' },
            { value: '5y', label: '5Y' },
          ]}
          value="5y"
          onChange={(value) => changes.push(value)}
        />,
      ),
    );
    const [oneYear, fiveYear] = host.querySelectorAll<HTMLButtonElement>('button');
    await act(async () => fiveYear?.click());
    await act(async () => oneYear?.click());
    expect(changes).toEqual(['1y']);
    await act(async () => root.unmount());
  });

  it('menu variant reads out the value and selects from a list', async () => {
    const changes: (number | null)[] = [];
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartToggleGroup
          variant="menu"
          allowDeselect
          label="Z"
          ariaLabel="Z-score window"
          options={[
            { value: 30, label: '30D', ariaLabel: '30-day trailing Z-score' },
            { value: 90, label: '90D', ariaLabel: '90-day trailing Z-score' },
          ]}
          value={30}
          onChange={(value) => changes.push(value)}
        />,
      ),
    );
    const trigger = host.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
    if (!trigger) throw new Error('menu trigger did not render');
    expect(trigger.textContent).toContain('30D');
    expect(trigger.ariaExpanded).toBe('false');

    await act(async () => trigger.click());
    const items = [...document.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')];
    expect(items.map((item) => item.textContent)).toEqual(['Off', '30D', '90D']);
    expect(items[1]?.ariaChecked).toBe('true');
    expect(document.activeElement).toBe(items[1]);

    await act(async () => items[2]?.click());
    expect(changes).toEqual([90]);
    expect(document.querySelector('[role="menu"]')).toBeNull();

    await act(async () => trigger.click());
    await act(async () =>
      document.querySelector<HTMLButtonElement>('[aria-label="Z-score window off"]')?.click(),
    );
    expect(changes).toEqual([90, null]);
    await act(async () => root.unmount());
  });
});
