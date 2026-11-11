/**
 * Interaction tests for CommandMenu: the ⌘K listener, lazy palette load, and router navigation.
 *
 * USAGE:
 *   pnpm exec vitest run src/ui/shell/CommandMenu.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { CommandMenu } from './CommandMenu';

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

let container: HTMLDivElement;
let root: Root;

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function StatefulCommandMenu() {
  const [open, setOpen] = useState(false);
  return <CommandMenu open={open} onOpenChange={setOpen} />;
}

async function mount() {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={['/catalog']}>
        <StatefulCommandMenu />
        <input data-testid="outside-field" />
        <Where />
      </MemoryRouter>,
    );
  });
}

async function pressCommandK(target: EventTarget = document.body, init: KeyboardEventInit = {}) {
  await act(async () => {
    target.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'k',
        metaKey: true,
        bubbles: true,
        cancelable: true,
        ...init,
      }),
    );
  });
  // Let the lazily imported palette chunk resolve and mount.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
}

function dialog() {
  return document.querySelector('[role="dialog"]');
}

function where() {
  return document.querySelector('[data-testid="where"]')?.textContent;
}

beforeEach(() => {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => {
    root.unmount();
  });
  container.remove();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('CommandMenu', () => {
  it('renders nothing until the shortcut is pressed', async () => {
    await mount();
    expect(dialog()).toBeNull();
    expect(document.querySelector('[cmdk-root]')).toBeNull();
  });

  it('opens on Cmd+K and on Ctrl+K, listing sections and Docs', async () => {
    await mount();
    await pressCommandK();
    expect(dialog()).not.toBeNull();
    const labels = [...document.querySelectorAll('.ui-command-item-label')].map(
      (node) => node.textContent,
    );
    expect(labels).toEqual(expect.arrayContaining(['Data', 'Signals', 'Strategies', 'Docs']));

    await pressCommandK(document.body, { metaKey: false, ctrlKey: true });
    expect(document.querySelector('[role="dialog"][data-open]')).toBeNull();
  });

  it('ignores the shortcut while focus is in a text field outside the palette', async () => {
    await mount();
    const field = document.querySelector<HTMLInputElement>('[data-testid="outside-field"]');
    if (!field) throw new Error('missing field');
    field.focus();
    await pressCommandK(field);
    expect(dialog()).toBeNull();
  });

  it('navigates through the router when a destination is chosen', async () => {
    await mount();
    await pressCommandK();
    const docs = [...document.querySelectorAll<HTMLElement>('[cmdk-item]')].find(
      (node) => node.querySelector('.ui-command-item-label')?.textContent === 'Docs',
    );
    if (!docs) throw new Error('Docs entry missing');
    await act(async () => {
      docs.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(where()).toBe('/docs');
    expect(document.querySelector('[role="dialog"][data-open]')).toBeNull();
  });
});
