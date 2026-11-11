/**
 * Structural tests for the shared ProgressBar primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/ProgressBar.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ProgressBar } from './ProgressBar';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ProgressBar', () => {
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

  it('carries the progressbar contract and fills to the completed fraction', () => {
    act(() => {
      root.render(<ProgressBar value={7} max={15} label="Completed validation fits" />);
    });

    const bar = container.querySelector('div.ui-progress-bar');
    if (!bar) throw new Error('missing progress bar');
    expect(bar.getAttribute('role')).toBe('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('7');
    expect(bar.getAttribute('aria-valuemax')).toBe('15');
    expect(bar.getAttribute('aria-label')).toBe('Completed validation fits');

    const fill = container.querySelector<HTMLElement>('.ui-progress-bar-fill');
    if (!fill) throw new Error('missing fill');
    expect(fill.style.width.startsWith('46.6')).toBe(true);
  });

  it('drops aria-valuemax and stays empty without a bound', () => {
    act(() => {
      root.render(<ProgressBar value={7} max={null} label="Completed validation fits" />);
    });

    const bar = container.querySelector('div.ui-progress-bar');
    if (!bar) throw new Error('missing progress bar');
    expect(bar.hasAttribute('aria-valuemax')).toBe(false);

    const fill = container.querySelector<HTMLElement>('.ui-progress-bar-fill');
    expect(fill?.style.width).toBe('0%');
  });
});
