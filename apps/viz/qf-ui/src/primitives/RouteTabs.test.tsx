/**
 * Active-state tests for the shared RouteTabs navigation.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/RouteTabs.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from '../../tests/memory-router';

import { RouteTabs } from './RouteTabs';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ITEMS = [
  { label: 'Overview', to: '/x' },
  { label: 'Assets', to: '/x/assets' },
  { label: 'Settings', to: '/x/settings' },
];

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('RouteTabs', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <MemoryRouter initialPath="/x/assets">
          <RouteTabs label="Example pages" items={ITEMS} />
        </MemoryRouter>,
      );
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('marks only the matching route as the current page', () => {
    const nav = container.querySelector('nav.ui-route-tabs[aria-label="Example pages"]');
    expect(nav).not.toBeNull();
    const links = Array.from(container.querySelectorAll('a'));
    const universe = links.find((link) => link.textContent === 'Assets');
    expect(universe?.getAttribute('aria-current')).toBe('page');
    expect(universe?.classList.contains('active')).toBe(true);
    // Tabs own their recipe: `.active` + this class is what RouteTabs.css keys
    // the brand underline off for NavLink callers.
    expect(universe?.classList.contains('ui-route-tabs-item')).toBe(true);
    for (const link of links.filter((link) => link.textContent !== 'Assets')) {
      expect(link.getAttribute('aria-current')).toBeNull();
      expect(link.classList.contains('active')).toBe(false);
    }
  });

  it('keeps the base item inactive on a child route through end semantics', () => {
    const overview = Array.from(container.querySelectorAll('a')).find(
      (link) => link.textContent === 'Overview',
    );
    expect(overview?.getAttribute('href')).toBe('/x');
    expect(overview?.classList.contains('active')).toBe(false);
  });
});
