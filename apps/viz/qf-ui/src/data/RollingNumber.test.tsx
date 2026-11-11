/**
 * Structural and behavioural tests for RollingNumber: reels, accessible value, change
 * direction and flash, formatting.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/RollingNumber.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { RollingNumber, type RollingNumberProps } from './RollingNumber';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('RollingNumber', () => {
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

  function show(props: RollingNumberProps): HTMLElement {
    act(() => root.render(<RollingNumber {...props} />));
    return container.firstElementChild as HTMLElement;
  }

  function translations(el: HTMLElement): string[] {
    return Array.from(
      el.querySelectorAll<HTMLElement>('.ui-rolling-number-reel'),
      (reel) => reel.style.transform,
    );
  }

  it('exposes the full value to assistive tech and hides the rolling glyphs', () => {
    const el = show({ value: 1234.5, format: (v) => Number(v).toFixed(2) });
    const live = el.querySelector('.sr-only');
    expect(live?.textContent).toBe('1234.50');
    expect(live?.getAttribute('aria-live')).toBe('polite');
    expect(el.querySelector('.ui-rolling-number-visual')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('rolls one reel per digit and renders separators as plain characters', () => {
    const el = show({ value: '12.5' });
    expect(translations(el)).toEqual(['translateY(-1em)', 'translateY(-2em)', 'translateY(-5em)']);
    expect(el.querySelectorAll('.ui-rolling-number-char')).toHaveLength(1);
    expect(el.querySelectorAll('.ui-rolling-number-cell')).toHaveLength(30);
  });

  it('applies Intl formatOptions to finite numbers', () => {
    const el = show({
      value: 1234.5,
      locale: 'en-US',
      formatOptions: { style: 'currency', currency: 'USD' },
    });
    expect(el.querySelector('.sr-only')?.textContent).toBe('$1,234.50');
  });

  it('starts without direction or flash', () => {
    const el = show({ value: 10 });
    expect(el.getAttribute('data-direction')).toBeNull();
    expect(el.getAttribute('data-flash')).toBeNull();
  });

  it('marks a rise as up, a fall as down, and alternates the flash to restart it', () => {
    show({ value: 10 });
    let el = show({ value: 11 });
    expect(el.getAttribute('data-direction')).toBe('up');
    const first = el.getAttribute('data-flash');
    expect(first === 'a' || first === 'b').toBe(true);

    el = show({ value: 9 });
    expect(el.getAttribute('data-direction')).toBe('down');
    expect(el.getAttribute('data-flash')).not.toBe(first);
  });

  it('skips the flash attribute when flash is off but still tracks direction', () => {
    show({ value: 10, flash: false });
    const el = show({ value: 12, flash: false });
    expect(el.getAttribute('data-direction')).toBe('up');
    expect(el.getAttribute('data-flash')).toBeNull();
  });

  it('keeps reels aligned to place value when the digit count changes', () => {
    show({ value: 99 });
    const el = show({ value: 100 });
    expect(translations(el)).toEqual(['translateY(-1em)', 'translateY(-0em)', 'translateY(-0em)']);
  });

  it('server-renders the value without a flash', () => {
    const markup = renderToStaticMarkup(<RollingNumber value={42} />);
    expect(markup).toContain('ui-rolling-number');
    expect(markup).not.toContain('data-flash');
  });
});
