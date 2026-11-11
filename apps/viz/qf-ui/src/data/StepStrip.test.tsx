/**
 * Structural tests for the shared StepStrip primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/StepStrip.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { StepStrip } from './StepStrip';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ITEMS = [
  { id: 'setup', label: 'Setup' },
  { id: 'fit', label: 'Fit' },
  { id: 'save', label: 'Save' },
];

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('StepStrip', () => {
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

  it('marks earlier steps complete, the current step current, and later steps upcoming', () => {
    act(() => {
      root.render(<StepStrip items={ITEMS} current={1} label="Training stages" />);
    });

    const list = container.querySelector('ol.ui-step-strip');
    expect(list?.getAttribute('aria-label')).toBe('Training stages');
    const items = [...container.querySelectorAll('li.ui-step-strip-item')];
    expect(items.map((item) => item.className)).toEqual([
      'ui-step-strip-item is-complete',
      'ui-step-strip-item is-current',
      'ui-step-strip-item is-upcoming',
    ]);
    expect(items.map((item) => item.getAttribute('aria-current'))).toEqual([null, 'step', null]);
  });

  it('leaves every step upcoming when no step is current', () => {
    act(() => {
      root.render(<StepStrip items={ITEMS} current={-1} label="Training stages" />);
    });

    const items = [...container.querySelectorAll('li.ui-step-strip-item')];
    expect(items).toHaveLength(3);
    expect(items.every((item) => item.classList.contains('is-upcoming'))).toBe(true);
    expect(container.querySelector('[aria-current]')).toBeNull();
  });
});
