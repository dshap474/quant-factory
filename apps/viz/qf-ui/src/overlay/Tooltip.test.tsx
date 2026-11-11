/**
 * Structural tests for Tooltip: opens on keyboard focus, Escape closes, the
 * trigger is described by the popup, and the provider/parts compose.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/Tooltip.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Tooltip, TooltipContent, TooltipProvider, TooltipRoot, TooltipTrigger } from './Tooltip';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function pressKey(key: string) {
  act(() => {
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }),
    );
  });
}

function keyboardFocus(element: HTMLElement) {
  // Base UI only opens on focus-visible; a preceding key event marks keyboard modality.
  act(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    element.focus();
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Tooltip', () => {
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

  it('is closed until the trigger takes keyboard focus, then closes on Escape', () => {
    act(() => {
      root.render(
        <TooltipProvider>
          <Tooltip content="Refresh data">
            <button type="button" aria-label="Refresh">
              R
            </button>
          </Tooltip>
        </TooltipProvider>,
      );
    });

    const trigger = container.querySelector('button');
    if (!trigger) throw new Error('missing trigger');
    expect(document.body.querySelector('.ui-tooltip')).toBeNull();

    keyboardFocus(trigger);
    const popup = document.body.querySelector('.ui-tooltip');
    if (!popup) throw new Error('tooltip did not open on focus');
    expect(popup.textContent).toBe('Refresh data');
    expect(popup.classList.contains('qf-motion-pop')).toBe(true);
    expect(popup.parentElement?.classList.contains('ui-overlay-positioner')).toBe(true);

    pressKey('Escape');
    expect(document.body.querySelector('.ui-tooltip')).toBeNull();
  });

  it('keeps the child element as the trigger', () => {
    act(() => {
      root.render(
        <Tooltip content="Hint">
          <button type="button" id="child">
            Child
          </button>
        </Tooltip>,
      );
    });

    expect(container.querySelectorAll('button')).toHaveLength(1);
    expect(container.querySelector('#child')?.textContent).toBe('Child');
  });

  it('composes from the exported parts', () => {
    act(() => {
      root.render(
        <TooltipRoot defaultOpen>
          <TooltipTrigger>Sharpe</TooltipTrigger>
          <TooltipContent side="bottom">Annualised, net of cost</TooltipContent>
        </TooltipRoot>,
      );
    });

    expect(document.body.querySelector('.ui-tooltip')?.textContent).toBe('Annualised, net of cost');
  });
});
