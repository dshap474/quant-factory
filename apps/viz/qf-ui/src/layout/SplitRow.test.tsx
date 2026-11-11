/**
 * DOM-order and modifier tests for the shared SplitRow layout.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/SplitRow.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { SplitRow } from './SplitRow';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SplitRow', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders the tag, label and fill modifier with the aside docked at the end', () => {
    act(() => {
      root.render(
        <SplitRow as="section" aria-label="x" fill aside={<aside>rail</aside>}>
          main
        </SplitRow>,
      );
    });
    const row = container.querySelector('section.ui-split-row.is-fill[aria-label="x"]');
    expect(row).not.toBeNull();
    expect(row?.firstElementChild?.className).toBe('ui-split-row-main');
    expect(row?.firstElementChild?.textContent).toBe('main');
    expect(row?.lastElementChild?.tagName).toBe('ASIDE');
  });

  it('docks the aside before the main column when asideSide is start', () => {
    act(() => {
      root.render(
        <SplitRow asideSide="start" aside={<aside>rail</aside>}>
          main
        </SplitRow>,
      );
    });
    const row = container.querySelector('.ui-split-row') as HTMLElement;
    expect(row.firstElementChild?.tagName).toBe('ASIDE');
    expect(row.lastElementChild?.className).toBe('ui-split-row-main');
  });
});
