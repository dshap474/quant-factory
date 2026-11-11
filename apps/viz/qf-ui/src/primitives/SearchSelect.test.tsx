/**
 * Combobox ARIA-wiring, keyboard-model, filtering, ranking and virtualization tests for SearchSelect.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/SearchSelect.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SearchSelect } from './SearchSelect';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
window.HTMLElement.prototype.scrollIntoView = () => undefined;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ITEMS = ['AAA', 'BBB', 'CCC'];
const VIEWPORT = 280;

/** jsdom has no layout: give every element a fixed viewport so the virtualizer sees a window. */
function stubLayout(): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 288,
    bottom: VIEWPORT,
    width: 288,
    height: VIEWPORT,
    toJSON: () => ({}),
  });
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(VIEWPORT);
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(288);
}

function pressKey(target: EventTarget, key: string) {
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  });
}

function typeQuery(input: HTMLInputElement, next: string) {
  const setValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  act(() => {
    setValue?.call(input, next);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SearchSelect', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    stubLayout();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  function renderSelect(
    value: string | null,
    onChange: (next: string | null) => void,
    items: readonly string[] = ITEMS,
  ) {
    act(() => {
      root.render(<SearchSelect label="asset" items={items} value={value} onChange={onChange} />);
    });
  }

  it('wears the shared focus-within recipe on the wrapper so one ring frames the composite', () => {
    renderSelect(null, () => undefined);

    expect(document.querySelector('.ui-search-select')?.classList.contains('qf-focus-within')).toBe(
      true,
    );
  });

  function openPanel() {
    const trigger = document.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]');
    if (!trigger) throw new Error('missing trigger');
    act(() => trigger.click());
  }

  function combobox(): HTMLInputElement {
    const input = document.querySelector<HTMLInputElement>('[role="combobox"]');
    if (!input) throw new Error('missing combobox input');
    return input;
  }

  it('keeps the search input outside the listbox and wires combobox ARIA', () => {
    renderSelect('AAA', () => undefined);
    openPanel();

    const input = combobox();
    const listbox = document.querySelector('[role="listbox"]');
    expect(listbox).not.toBeNull();
    expect(listbox?.contains(input)).toBe(false);
    expect(input.getAttribute('aria-controls')).toBe(listbox?.id);
    expect(input.getAttribute('aria-autocomplete')).toBe('list');
    expect(listbox?.parentElement?.className).toContain('ui-scroll-area');

    const options = document.querySelectorAll('[role="option"]');
    expect(options).toHaveLength(ITEMS.length);
    expect(options[0]?.getAttribute('aria-selected')).toBe('true');
    expect(options[1]?.getAttribute('aria-selected')).toBe('false');
    expect(options[0]?.className).toContain('is-selected');
  });

  it('moves the active option with arrow keys via aria-activedescendant', () => {
    renderSelect(null, () => undefined);
    openPanel();

    const input = combobox();
    expect(input.getAttribute('aria-activedescendant')).toBeNull();

    pressKey(input, 'ArrowDown');
    const options = document.querySelectorAll('[role="option"]');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0]?.id);
    expect(options[0]?.hasAttribute('data-highlighted')).toBe(true);

    pressKey(input, 'ArrowDown');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[1]?.id);

    pressKey(input, 'ArrowUp');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0]?.id);

    pressKey(input, 'ArrowUp');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[2]?.id);

    pressKey(input, 'End');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[2]?.id);

    pressKey(input, 'Home');
    expect(input.getAttribute('aria-activedescendant')).toBe(options[0]?.id);
  });

  it('selects the active option on Enter and closes the panel', () => {
    const onChange = vi.fn();
    renderSelect(null, onChange);
    openPanel();

    const input = combobox();
    pressKey(input, 'ArrowDown');
    pressKey(input, 'ArrowDown');
    pressKey(input, 'Enter');

    expect(onChange).toHaveBeenCalledWith('BBB');
    expect(document.querySelector('[role="combobox"]')).toBeNull();
  });

  it('closes on Escape without selecting', () => {
    const onChange = vi.fn();
    renderSelect(null, onChange);
    openPanel();

    pressKey(combobox(), 'Escape');

    expect(onChange).not.toHaveBeenCalled();
    expect(document.querySelector('[role="combobox"]')).toBeNull();
  });

  it('filters options by the search query and shows the empty note', () => {
    renderSelect(null, () => undefined);
    openPanel();

    typeQuery(combobox(), 'bb');
    let options = document.querySelectorAll('[role="option"]');
    expect(options).toHaveLength(1);
    expect(options[0]?.textContent).toBe('BBB');

    typeQuery(combobox(), 'zzz');
    options = document.querySelectorAll('[role="option"]');
    expect(options).toHaveLength(0);
    expect(document.body.textContent).toContain('No matches');
  });

  it('ranks exact, then prefix, then substring matches', () => {
    renderSelect(null, () => undefined, ['wbtc', 'btcdom', 'eth', 'btc']);
    openPanel();

    typeQuery(combobox(), 'BTC');
    const labels = [...document.querySelectorAll('[role="option"]')].map((o) => o.textContent);
    expect(labels).toEqual(['btc', 'btcdom', 'wbtc']);
  });

  it('makes the best match active so Enter takes it without arrowing', () => {
    const onChange = vi.fn();
    renderSelect(null, onChange, ['wbtc', 'btcdom', 'btc']);
    openPanel();

    typeQuery(combobox(), 'btc');
    pressKey(combobox(), 'Enter');
    expect(onChange).toHaveBeenCalledWith('btc');
  });

  it('virtualizes long rosters into one scroll list without pages', () => {
    const roster = Array.from({ length: 600 }, (_, i) => `A${i}`);
    renderSelect(null, () => undefined, roster);
    openPanel();

    const mounted = document.querySelectorAll('[role="option"]');
    expect(mounted.length).toBeGreaterThan(0);
    expect(mounted.length).toBeLessThan(40);
    expect(mounted[0]?.getAttribute('aria-setsize')).toBe('600');
    expect(document.querySelector('nav[aria-label="Pagination"]')).toBeNull();
    expect(document.body.textContent).toContain('600 assets');

    typeQuery(combobox(), 'A59');
    expect(document.body.textContent).toContain('11 of 600');
  });

  it('highlights the matched text inside each option', () => {
    renderSelect(null, () => undefined, ['wbtc']);
    openPanel();

    typeQuery(combobox(), 'bt');
    expect(document.querySelector('.ui-search-select-match')?.textContent).toBe('bt');
  });
});
