/**
 * Structural tests for Dialog and Sheet: open via trigger, Escape closes, the
 * title and description wire aria-labelledby / aria-describedby, and the
 * footer, close button, and motion classes render.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/Dialog.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Dialog } from './Dialog';
import { Sheet } from './Sheet';

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

describe('Dialog and Sheet', () => {
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

  it('opens a modal dialog from its trigger with title and description wired', () => {
    act(() => {
      root.render(
        <Dialog
          trigger={<button type="button" />}
          triggerLabel="Rename"
          title="Rename run"
          description="The new name replaces the label."
          footer={<span data-testid="footer">actions</span>}
        >
          <p>body</p>
        </Dialog>,
      );
    });

    const trigger = container.querySelector('button');
    if (!trigger) throw new Error('missing trigger');
    expect(trigger.textContent).toBe('Rename');
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();

    click(trigger);
    const popup = document.body.querySelector('[role="dialog"]');
    if (!popup) throw new Error('dialog did not open');
    const title = popup.querySelector('.ui-dialog-title');
    const description = popup.querySelector('.ui-dialog-description');
    expect(title?.textContent).toBe('Rename run');
    expect(popup.getAttribute('aria-labelledby')).toBe(title?.id);
    expect(popup.getAttribute('aria-describedby')).toBe(description?.id);
    expect(popup.classList.contains('qf-motion-pop')).toBe(true);
    expect(document.body.querySelector('.ui-overlay-backdrop.qf-motion-fade')).not.toBeNull();
    expect(popup.querySelector('.ui-dialog-footer [data-testid="footer"]')).not.toBeNull();
    expect(popup.querySelector('.ui-dialog-body')?.textContent).toBe('body');
    expect(popup.querySelector('button[aria-label="Close"]')).not.toBeNull();

    pressKey('Escape');
    expect(document.body.querySelector('[role="dialog"]')).toBeNull();
  });

  it('reports open changes when controlled, including the close button', () => {
    const onOpenChange = vi.fn();
    act(() => {
      root.render(
        <Dialog open onOpenChange={onOpenChange} title="Delete?" description="Cannot be undone." />,
      );
    });

    const close = document.body.querySelector('button[aria-label="Close"]');
    if (!close) throw new Error('missing close button');
    click(close);
    expect(onOpenChange).toHaveBeenCalledTimes(1);
    expect(onOpenChange.mock.calls[0]?.[0]).toBe(false);
  });

  it('renders the sheet as a right-edge dialog with the sheet motion class', () => {
    act(() => {
      root.render(
        <Sheet open title="Run details" description="Inputs and outputs.">
          <p>detail</p>
        </Sheet>,
      );
    });

    const popup = document.body.querySelector('[role="dialog"]');
    if (!popup) throw new Error('sheet did not open');
    expect(popup.classList.contains('ui-sheet')).toBe(true);
    expect(popup.classList.contains('qf-motion-sheet-right')).toBe(true);
    expect(popup.getAttribute('aria-labelledby')).toBe(popup.querySelector('.ui-dialog-title')?.id);
    expect(popup.textContent).toContain('detail');
  });
});
