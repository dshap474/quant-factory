/**
 * Structural tests for Toast: `toast()` renders on the tone surface in the
 * bottom-right viewport, announces, dismisses, and `useToast` shares the manager.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/Toast.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Toaster } from './Toast';
import { dismissToast, toast, useToast } from './toast-store';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function click(element: Element) {
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

function ToastButton() {
  const { toast: show } = useToast();
  return (
    <button
      type="button"
      onClick={() => show({ title: 'Copied', description: 'run-001', tone: 'success' })}
    >
      copy
    </button>
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Toast', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => dismissToast());
    act(() => root.unmount());
    container.remove();
  });

  it('shows a toned toast with title and description in the viewport', () => {
    act(() => {
      root.render(<Toaster />);
    });
    expect(document.body.querySelector('.ui-toast-viewport')).not.toBeNull();
    expect(document.body.querySelector('.ui-toast')).toBeNull();

    act(() => {
      toast({ title: 'Saved', description: 'Layout stored', tone: 'warning' });
    });

    const item = document.body.querySelector('.ui-toast');
    if (!item) throw new Error('toast did not render');
    expect(item.getAttribute('data-tone')).toBe('warning');
    expect(item.classList.contains('qf-motion-sheet-bottom')).toBe(true);
    expect(item.querySelector('.ui-toast-title')?.textContent).toBe('Saved');
    expect(item.querySelector('.ui-toast-description')?.textContent).toBe('Layout stored');
    expect(item.closest('.ui-toast-viewport')).not.toBeNull();
  });

  it('defaults to the neutral tone and dismisses from the close button', () => {
    act(() => {
      root.render(<Toaster />);
    });
    act(() => {
      toast({ title: 'Hello' });
    });

    const item = document.body.querySelector('.ui-toast');
    if (!item) throw new Error('toast did not render');
    expect(item.getAttribute('data-tone')).toBe('neutral');
    expect(item.querySelector('.ui-toast-description')).toBeNull();

    const close = item.querySelector('button[aria-label="Dismiss"]');
    if (!close) throw new Error('missing close button');
    click(close);
    expect(item.getAttribute('data-ending-style')).not.toBeNull();
  });

  it('lets components raise toasts through useToast', () => {
    act(() => {
      root.render(
        <>
          <Toaster />
          <ToastButton />
        </>,
      );
    });

    const button = container.querySelector('button');
    if (!button) throw new Error('missing button');
    click(button);
    const item = document.body.querySelector('.ui-toast');
    expect(item?.getAttribute('data-tone')).toBe('success');
    expect(item?.querySelector('.ui-toast-title')?.textContent).toBe('Copied');
  });
});
