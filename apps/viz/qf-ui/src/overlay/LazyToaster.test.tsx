/**
 * LazyToaster renders nothing until the first toast, then loads the Base UI
 * renderer and flushes the toast raised before it mounted.
 *
 * USAGE:
 *   pnpm exec vitest run src/overlay/LazyToaster.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it, vi } from 'vitest';

import { LazyToaster } from './LazyToaster';
import { dismissToast, toast } from './toast-store';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('LazyToaster', () => {
  it('stays empty until a toast, then shows the buffered toast', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => root.render(<LazyToaster />));
    expect(document.body.querySelector('.ui-toast-viewport')).toBeNull();

    act(() => {
      toast({ title: 'Buffered', tone: 'info' });
    });
    await vi.waitFor(() => {
      expect(document.body.querySelector('.ui-toast')?.textContent).toContain('Buffered');
    });

    act(() => dismissToast());
    act(() => root.unmount());
    container.remove();
  });
});
