/**
 * Structural tests for Popover and InfoTip: open via trigger, Escape closes,
 * aria wiring between trigger and popup.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/Popover.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { InfoTip } from './InfoTip';
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverTitle,
  PopoverTrigger,
} from './Popover';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

function pressKey(key: string) {
  act(() => {
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }),
    );
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Popover', () => {
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

  it('opens from the trigger, wires aria, and closes on Escape', () => {
    act(() => {
      root.render(
        <Popover>
          <PopoverTrigger>Filters</PopoverTrigger>
          <PopoverContent>
            <PopoverTitle>Filters</PopoverTitle>
            <PopoverDescription>Narrow the run list.</PopoverDescription>
          </PopoverContent>
        </Popover>,
      );
    });

    const trigger = container.querySelector('button');
    if (!trigger) throw new Error('missing trigger');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(document.body.querySelector('.ui-popover')).toBeNull();

    click(trigger);
    const popup = document.body.querySelector('.ui-popover');
    if (!popup) throw new Error('popover did not open');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(popup.classList.contains('qf-motion-pop')).toBe(true);
    expect(popup.textContent).toContain('Narrow the run list.');
    expect(popup.getAttribute('aria-labelledby')).toBe(
      popup.querySelector('.ui-popover-title')?.id,
    );

    pressKey('Escape');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });
});

describe('InfoTip', () => {
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

  it('renders a labelled icon button that reveals the explanation on click', () => {
    act(() => {
      root.render(<InfoTip content="8h annualised, median across venues." />);
    });

    const trigger = container.querySelector('button.ui-info-tip-trigger');
    if (!trigger) throw new Error('missing trigger');
    expect(trigger.getAttribute('aria-label')).toBe('More info');
    expect(trigger.querySelector('svg')).not.toBeNull();

    click(trigger);
    expect(document.body.querySelector('.ui-info-tip')?.textContent).toBe(
      '8h annualised, median across venues.',
    );

    pressKey('Escape');
    expect(document.body.querySelector('.ui-info-tip')).toBeNull();
  });

  it('honours a custom accessible label', () => {
    act(() => {
      root.render(<InfoTip content="Two-way." label="About turnover" />);
    });

    expect(container.querySelector('button')?.getAttribute('aria-label')).toBe('About turnover');
  });
});
