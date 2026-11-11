/**
 * Interaction contract for accessible chart-title information.
 *
 * USAGE:
 *   pnpm test -- chart-info-popover.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ChartInfoPopover } from '../../src/charts/components/ChartInfoPopover';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartInfoPopover', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('reveals chart guidance on hover and hides it when the pointer leaves', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartInfoPopover
          chartTitle="Price history"
          sections={[{ label: 'How to read', content: 'Compare the two series.' }]}
        />,
      ),
    );
    const button = host.querySelector<HTMLButtonElement>('button');
    if (!button) throw new Error('chart info button did not render');

    await act(async () => button.dispatchEvent(new Event('pointerover', { bubbles: true })));
    const tooltip = document.body.querySelector<HTMLElement>('[role="tooltip"]');
    expect(tooltip?.textContent).toContain('About Price history');
    expect(tooltip?.textContent).toContain('Compare the two series.');
    expect(button.getAttribute('aria-describedby')).toBe(tooltip?.id);

    await act(async () => button.dispatchEvent(new Event('pointerout', { bubbles: true })));
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();
    await act(async () => root.unmount());
  });

  it('supports keyboard focus and Escape dismissal', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartInfoPopover
          chartTitle="Series overview"
          sections={[{ label: 'Metrics', content: 'Two daily series on a shared axis.' }]}
        />,
      ),
    );
    const button = host.querySelector<HTMLButtonElement>('button');
    if (!button) throw new Error('chart info button did not render');

    await act(async () => button.focus());
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toContain(
      'Two daily series on a shared axis.',
    );

    await act(async () =>
      button.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
      ),
    );
    expect(document.body.querySelector('[role="tooltip"]')).toBeNull();
    expect(document.activeElement).toBe(button);
    await act(async () => root.unmount());
  });
});
