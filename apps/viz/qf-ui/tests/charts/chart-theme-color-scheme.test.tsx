/**
 * `useChartTheme` color-scheme subscription contract.
 *
 * USAGE:
 *   pnpm test -- tests/charts/chart-theme-color-scheme.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useChartTheme } from '../../src/charts/hooks/useChartTheme';
import { QF_DARK_THEME, QF_LIGHT_THEME } from '../../src/charts/theme/defaults';

// --------------------------------------------------------------------------- #
// Controllable media query
// --------------------------------------------------------------------------- #

const listeners = new Map<string, Set<() => void>>();
const state = { light: false };

function installMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({
      get matches() {
        return query.includes('light') ? state.light : !state.light;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, callback: () => void) => {
        const bucket = listeners.get(query) ?? new Set<() => void>();
        bucket.add(callback);
        listeners.set(query, bucket);
      },
      removeEventListener: (_type: string, callback: () => void) => {
        listeners.get(query)?.delete(callback);
      },
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('useChartTheme color scheme', () => {
  let host: HTMLDivElement;
  let rendered: string[];

  function Probe() {
    rendered.push(useChartTheme().axis);
    return null;
  }

  beforeEach(() => {
    listeners.clear();
    state.light = false;
    rendered = [];
    installMatchMedia();
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('re-renders charts when the preferred color scheme changes', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<Probe />));

    expect(rendered.at(-1)).toBe(QF_DARK_THEME.axisLabel);

    state.light = true;
    await act(async () => {
      for (const bucket of listeners.values()) for (const callback of bucket) callback();
    });

    expect(rendered.at(-1)).toBe(QF_LIGHT_THEME.axisLabel);
    await act(async () => root.unmount());
  });

  it('unsubscribes from the media query on unmount', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<Probe />));
    const subscribed = [...listeners.values()].reduce((total, set) => total + set.size, 0);
    expect(subscribed).toBeGreaterThan(0);

    await act(async () => root.unmount());
    const remaining = [...listeners.values()].reduce((total, set) => total + set.size, 0);
    expect(remaining).toBe(0);
  });
});
