/**
 * Selection, keyboard and typeahead tests for the shared ColumnBrowser.
 *
 * USAGE:
 *   pnpm exec vitest run src/data/ColumnBrowser.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ColumnBrowser, type ColumnBrowserOption, typeaheadIndex } from './ColumnBrowser';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Fixture
// --------------------------------------------------------------------------- #

const FAMILIES = ['alpha', 'beta', 'bravo'];
const VERSIONS: ColumnBrowserOption[] = [
  { value: 'v002', meta: '2026-09-30' },
  { value: 'v001', meta: '2026-09-28' },
];

function Harness() {
  const [family, setFamily] = useState('alpha');
  const [version, setVersion] = useState('v002');
  return (
    <ColumnBrowser
      ariaLabel="Pick"
      columns={[
        {
          id: 'family',
          label: 'Strategy',
          value: family,
          onValueChange: setFamily,
          options: FAMILIES.map((value) => ({ value })),
        },
        {
          id: 'version',
          label: 'Version',
          value: version,
          onValueChange: setVersion,
          options: VERSIONS,
        },
      ]}
    />
  );
}

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
  act(() => root.render(<Harness />));
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function lists(): [HTMLElement, HTMLElement] {
  const [families, versions] = host.querySelectorAll<HTMLElement>('[role="listbox"]');
  if (!families || !versions) throw new Error('expected two listboxes');
  return [families, versions];
}
const selectedIn = (list: HTMLElement) =>
  list.querySelector('[aria-selected="true"]')?.textContent ?? null;
const press = (target: HTMLElement, key: string) =>
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  });

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ColumnBrowser', () => {
  it('renders one labelled listbox per column with label, meta and count', () => {
    const [families, versions] = lists();
    expect(host.querySelectorAll('[role="listbox"]')).toHaveLength(2);
    expect(families.getAttribute('aria-labelledby')).toBeTruthy();
    expect(host.textContent).toContain('Strategy3');
    expect(selectedIn(versions)).toBe('v0022026-09-30');
    expect(versions.getAttribute('aria-activedescendant')).toBe(
      versions.querySelector('[aria-selected="true"]')?.id,
    );
  });

  it('selects on click', () => {
    const [families] = lists();
    act(() => families.querySelectorAll<HTMLElement>('[role="option"]')[2]?.click());
    expect(selectedIn(families)).toBe('bravo');
  });

  it('moves the selection with arrows, Home and End, and focus across columns', () => {
    const [families, versions] = lists();
    press(families, 'ArrowDown');
    expect(selectedIn(families)).toBe('beta');
    press(families, 'End');
    expect(selectedIn(families)).toBe('bravo');
    press(families, 'ArrowDown');
    expect(selectedIn(families)).toBe('bravo');
    press(families, 'Home');
    expect(selectedIn(families)).toBe('alpha');
    families.focus();
    press(families, 'ArrowRight');
    expect(document.activeElement).toBe(versions);
  });

  it('jumps by typed prefix', () => {
    const [families] = lists();
    press(families, 'b');
    expect(selectedIn(families)).toBe('beta');
    press(families, 'r');
    expect(selectedIn(families)).toBe('bravo');
  });

  it('cycles a repeated first letter and wraps', () => {
    const options = FAMILIES.map((value) => ({ value }));
    expect(typeaheadIndex(options, 'b', 1)).toBe(2);
    expect(typeaheadIndex(options, 'b', 2)).toBe(1);
    expect(typeaheadIndex(options, 'z', 0)).toBe(-1);
  });
});
