/**
 * Tests for useSearchParamState through the qf-ui router adapter: a host adapter
 * supplies the params, and without one the History API fallback reads and
 * writes `window.location`.
 *
 * USAGE:
 *   pnpm exec vitest run src/router/useSearchParamState.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';

import { LocationProbe, MemoryRouter } from '../../tests/memory-router';
import { useSearchParamState } from './useSearchParamState';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function ViewPicker() {
  const [view, setView] = useSearchParamState('view', 'live');
  return (
    <div>
      <span data-testid="view">{view}</span>
      <button type="button" onClick={() => setView('history')}>
        next
      </button>
    </div>
  );
}

function mount(ui: ReactNode): { node: HTMLDivElement; unmount: () => void } {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const node = document.createElement('div');
  const root = createRoot(node);
  act(() => root.render(ui));
  return { node, unmount: () => act(() => root.unmount()) };
}

function clickNext(node: HTMLElement) {
  act(() => {
    node.querySelector<HTMLButtonElement>('button')?.click();
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('useSearchParamState', () => {
  it('reads and writes the host adapter search params, keeping other keys', () => {
    const { node, unmount } = mount(
      <MemoryRouter initialPath="/signals?q=a">
        <ViewPicker />
        <LocationProbe />
      </MemoryRouter>,
    );
    expect(node.querySelector('[data-testid="view"]')?.textContent).toBe('live');
    expect(node.querySelector('[data-testid="location"]')?.textContent).toBe('/signals?q=a');

    clickNext(node);
    expect(node.querySelector('[data-testid="view"]')?.textContent).toBe('history');
    expect(node.querySelector('[data-testid="location"]')?.textContent).toBe(
      '/signals?q=a&view=history',
    );
    unmount();
  });

  it('falls back to the History API without a router provider', () => {
    window.history.replaceState(null, '', '/docs?view=table');
    const { node, unmount } = mount(<ViewPicker />);
    expect(node.querySelector('[data-testid="view"]')?.textContent).toBe('table');

    clickNext(node);
    expect(window.location.search).toBe('?view=history');
    expect(node.querySelector('[data-testid="view"]')?.textContent).toBe('history');
    unmount();
  });
});
