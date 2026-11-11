/**
 * Structural tests for DropdownMenu: opens from the trigger, exposes menu
 * roles, items fire and close, checkbox items toggle, Escape closes.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/DropdownMenu.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './DropdownMenu';

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

function openMenu(container: HTMLElement): HTMLElement {
  const trigger = container.querySelector('button');
  if (!trigger) throw new Error('missing trigger');
  // Base UI opens the menu on mousedown, not click.
  act(() => {
    trigger.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }),
    );
    trigger.dispatchEvent(
      new MouseEvent('mouseup', { bubbles: true, cancelable: true, button: 0 }),
    );
    trigger.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }));
  });
  return trigger;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DropdownMenu', () => {
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

  it('opens a menu of items, runs an item, and closes', () => {
    const onRename = vi.fn();
    act(() => {
      root.render(
        <DropdownMenu>
          <DropdownMenuTrigger>Options</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel>Run</DropdownMenuLabel>
            <DropdownMenuItem onClick={onRename}>Rename</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>Delete</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>,
      );
    });

    expect(document.body.querySelector('[role="menu"]')).toBeNull();
    const trigger = openMenu(container);
    const menu = document.body.querySelector('[role="menu"]');
    if (!menu) throw new Error('menu did not open');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(menu.classList.contains('qf-motion-pop')).toBe(true);
    expect(menu.querySelectorAll('[role="menuitem"]')).toHaveLength(2);
    expect(menu.querySelector('.ui-menu-label')?.textContent).toBe('Run');
    expect(menu.querySelector('[role="separator"]')).not.toBeNull();
    expect(menu.querySelectorAll('[role="menuitem"]')[1]?.hasAttribute('data-disabled')).toBe(true);

    const rename = menu.querySelector('[role="menuitem"]');
    if (!rename) throw new Error('missing item');
    click(rename);
    expect(onRename).toHaveBeenCalledTimes(1);
    expect(document.body.querySelector('[role="menu"]')).toBeNull();
  });

  it('toggles a checkbox item and closes on Escape', () => {
    const onCheckedChange = vi.fn();
    act(() => {
      root.render(
        <DropdownMenu>
          <DropdownMenuTrigger>Options</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuCheckboxItem checked={false} onCheckedChange={onCheckedChange}>
              Pinned
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>,
      );
    });

    openMenu(container);
    const item = document.body.querySelector('[role="menuitemcheckbox"]');
    if (!item) throw new Error('missing checkbox item');
    expect(item.getAttribute('aria-checked')).toBe('false');
    click(item);
    expect(onCheckedChange).toHaveBeenCalledTimes(1);
    expect(onCheckedChange.mock.calls[0]?.[0]).toBe(true);

    // Checkbox items keep the menu open after toggling; Escape closes it.
    expect(document.body.querySelector('[role="menu"]')).not.toBeNull();
    pressKey('Escape');
    expect(document.body.querySelector('[role="menu"]')).toBeNull();
  });
});
