/**
 * Index chip and wrapping-description behaviour for IndexBar.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/IndexBar.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { IndexBar } from './IndexBar';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('IndexBar', () => {
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

  it('renders the index chip first when index is set', () => {
    act(() => root.render(<IndexBar index="01" title="Universe" />));

    const bar = container.querySelector('.index-bar') as HTMLElement;
    expect(bar.classList.contains('is-indexed')).toBe(true);

    const chip = bar.firstElementChild as HTMLElement;
    expect(chip.className).toBe('index-bar-index');
    expect(chip.getAttribute('aria-hidden')).toBe('true');
    expect(chip.textContent).toBe('01');
  });

  it('renders no chip without an index', () => {
    act(() => root.render(<IndexBar title="Universe" />));

    const bar = container.querySelector('.index-bar') as HTMLElement;
    expect(bar.classList.contains('is-indexed')).toBe(false);
    expect(container.querySelector('.index-bar-index')).toBeNull();
  });

  it('marks the row as wrapping when wrap is set', () => {
    act(() => root.render(<IndexBar title="Universe" description="Long line" wrap />));

    const bar = container.querySelector('.index-bar') as HTMLElement;
    expect(bar.classList.contains('is-wrap')).toBe(true);
  });
});
