/**
 * Behaviour tests for CommandPalette: dialog wiring, filtering, selection, and Escape.
 *
 * USAGE:
 *   pnpm exec vitest run src/command/CommandPalette.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { type CommandGroup, CommandPalette } from './CommandPalette';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
window.HTMLElement.prototype.scrollIntoView = () => undefined;
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const onData = vi.fn();
const onSignals = vi.fn();
const onDocs = vi.fn();

const GROUPS: CommandGroup[] = [
  {
    id: 'go',
    heading: 'Go to',
    items: [
      { id: 'data', label: 'Data', hint: '/catalog', onSelect: onData },
      {
        id: 'signals',
        label: 'Signals',
        hint: '/signals',
        keywords: ['alpha'],
        onSelect: onSignals,
      },
    ],
  },
  { id: 'help', heading: 'Help', items: [{ id: 'docs', label: 'Docs', onSelect: onDocs }] },
];

function Harness({ initialOpen }: { initialOpen: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  return (
    <>
      <button type="button" data-testid="open" onClick={() => setOpen(true)}>
        open
      </button>
      <CommandPalette open={open} onOpenChange={setOpen} groups={GROUPS} />
    </>
  );
}

function typeQuery(input: HTMLInputElement, next: string) {
  const setValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
  act(() => {
    setValue?.call(input, next);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

function pressKey(target: EventTarget, key: string) {
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  });
}

function input(): HTMLInputElement {
  const found = document.querySelector<HTMLInputElement>('[cmdk-input]');
  if (!found) throw new Error('palette input not rendered');
  return found;
}

function itemLabels(): string[] {
  return [...document.querySelectorAll('.ui-command-item-label')].map(
    (node) => node.textContent ?? '',
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('CommandPalette', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.clearAllMocks();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders nothing while closed', () => {
    act(() => root.render(<Harness initialOpen={false} />));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it('renders a labelled dialog with grouped items and footer hints when open', () => {
    act(() => root.render(<Harness initialOpen />));
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog?.hasAttribute('data-open')).toBe(true);
    expect(dialog?.getAttribute('aria-labelledby')).toBeTruthy();
    expect(dialog?.textContent).toContain('Command menu');
    expect(document.querySelector('.ui-command-footer')?.textContent).toContain('navigate');
    expect(itemLabels()).toHaveLength(3);
    expect(document.body.textContent).toContain('Go to');
  });

  it('opens from the trigger the host wires to it', () => {
    act(() => root.render(<Harness initialOpen={false} />));
    act(() => {
      document
        .querySelector<HTMLButtonElement>('[data-testid="open"]')
        ?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  });

  it('filters by label and by keyword, and shows the empty state', () => {
    act(() => root.render(<Harness initialOpen />));

    typeQuery(input(), 'sig');
    expect(itemLabels()).toEqual(['Signals']);

    typeQuery(input(), 'alpha');
    expect(itemLabels()).toEqual(['Signals']);

    typeQuery(input(), 'zzzz');
    expect(itemLabels()).toEqual([]);
    expect(document.querySelector('[cmdk-empty]')?.textContent).toBe('No results.');
  });

  it('runs onSelect and closes when an item is chosen', () => {
    act(() => root.render(<Harness initialOpen />));
    typeQuery(input(), 'docs');

    const item = document.querySelector('[cmdk-item]');
    act(() => {
      item?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(onDocs).toHaveBeenCalledTimes(1);
    expect(onData).not.toHaveBeenCalled();
    // The exit transition may keep the popup mounted briefly; the open state is what closes.
    expect(document.querySelector('[role="dialog"][data-open]')).toBeNull();
  });

  it('selects the highlighted item with Enter after arrow navigation', () => {
    act(() => root.render(<Harness initialOpen />));
    const field = input();
    pressKey(field, 'ArrowDown');
    pressKey(field, 'Enter');
    expect(onSignals).toHaveBeenCalledTimes(1);
  });

  it('closes on Escape', () => {
    act(() => root.render(<Harness initialOpen />));
    pressKey(input(), 'Escape');
    expect(document.querySelector('[role="dialog"][data-open]')).toBeNull();
  });
});
