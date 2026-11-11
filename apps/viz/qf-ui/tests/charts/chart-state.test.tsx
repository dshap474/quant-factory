/**
 * Rendering contract for the in-frame chart status block.
 *
 * USAGE:
 *   pnpm test -- tests/charts/chart-state.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ChartState } from '../../src/charts/components/ChartState';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartState', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('announces an error with its message and action', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartState
          status="error"
          message="Source unavailable"
          action={<button type="button">Retry source</button>}
        />,
      ),
    );

    const block = host.querySelector<HTMLDivElement>('div.qf-chart-state');
    expect(block?.getAttribute('data-status')).toBe('error');
    expect(block?.getAttribute('role')).toBe('alert');
    expect(block?.querySelector('.qf-chart-state-message')?.textContent).toBe('Source unavailable');
    expect(block?.querySelector('button')?.textContent).toBe('Retry source');

    await act(async () => root.unmount());
  });

  it('shows a skeleton for loading and keeps the message as the accessible label only', async () => {
    const root = createRoot(host);
    await act(async () => root.render(<ChartState status="loading" message="Loading series" />));

    const block = host.querySelector<HTMLDivElement>('div.qf-chart-state');
    expect(block?.getAttribute('data-status')).toBe('loading');
    expect(block?.getAttribute('role')).toBe('status');
    expect(block?.getAttribute('aria-label')).toBe('Loading series');
    expect(block?.querySelector('.qf-chart-state-skeleton')).not.toBeNull();
    expect(block?.textContent).toBe('');

    await act(async () => root.unmount());
  });
});
