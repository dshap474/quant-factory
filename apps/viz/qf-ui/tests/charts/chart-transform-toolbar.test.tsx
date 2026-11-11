/**
 * Interaction tests for the controlled chart transform toolbar.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/chart-transform-toolbar.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { ChartTransformState } from '../../src/charts/charts/timeSeriesTransforms';
import { ChartTransformToolbar } from '../../src/charts/components/ChartTransformToolbar';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartTransformToolbar', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('toggles exclusive windows per transform while allowing Z-score and EMA together', async () => {
    function Harness() {
      const [value, setValue] = useState<ChartTransformState>({ zScore: null, ema: null });
      return (
        <ChartTransformToolbar
          controls={{ zScore: true, ema: true }}
          value={value}
          onChange={setValue}
        />
      );
    }

    const root = createRoot(host);
    await act(async () => root.render(<Harness />));
    const z30 = host.querySelector<HTMLButtonElement>('[aria-label="30-day trailing Z-score"]');
    const z90 = host.querySelector<HTMLButtonElement>('[aria-label="90-day trailing Z-score"]');
    const z180 = host.querySelector<HTMLButtonElement>('[aria-label="180-day trailing Z-score"]');
    const z365 = host.querySelector<HTMLButtonElement>('[aria-label="365-day trailing Z-score"]');
    const ema30 = host.querySelector<HTMLButtonElement>('[aria-label="30-day EMA smoothing"]');
    expect(host.querySelectorAll('button')).toHaveLength(6);
    if (!z30 || !z90 || !z180 || !z365 || !ema30) {
      throw new Error('transform controls did not render');
    }

    await act(async () => z30.click());
    expect(z30.ariaPressed).toBe('true');
    await act(async () => z90.click());
    expect(z30.ariaPressed).toBe('false');
    expect(z90.ariaPressed).toBe('true');
    await act(async () => z365.click());
    expect(z90.ariaPressed).toBe('false');
    expect(z365.ariaPressed).toBe('true');
    await act(async () => ema30.click());
    expect(z365.ariaPressed).toBe('true');
    expect(ema30.ariaPressed).toBe('true');
    await act(async () => z365.click());
    expect(z365.ariaPressed).toBe('false');
    expect(ema30.ariaPressed).toBe('true');

    await act(async () => root.unmount());
  });

  it('supports chart-specific EMA windows without adding Z-score controls', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartTransformToolbar
          controls={{ ema: [30, 90, 180, 365] }}
          value={{ zScore: null, ema: null }}
          onChange={() => undefined}
        />,
      ),
    );

    expect(host.querySelectorAll('button[aria-label*="EMA smoothing"]')).toHaveLength(4);
    expect(host.querySelector('[aria-label="365-day EMA smoothing"]')).not.toBeNull();
    expect(host.querySelector('[aria-label*="trailing Z-score"]')).toBeNull();

    await act(async () => root.unmount());
  });
});
