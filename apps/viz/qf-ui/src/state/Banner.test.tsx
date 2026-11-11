/**
 * Structural tests for the shared Banner notice band.
 *
 * USAGE:
 *   pnpm exec vitest run src/state/Banner.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { Banner } from './Banner';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Banner', () => {
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

  it('announces an informational notice by default', () => {
    act(() => {
      root.render(<Banner>2 malformed run sidecars omitted</Banner>);
    });

    const banner = container.querySelector('div.ui-banner.is-info');
    if (!banner) throw new Error('missing banner');
    expect(banner.getAttribute('role')).toBe('status');
    expect(banner.textContent).toBe('2 malformed run sidecars omitted');
  });

  it('raises an alert for the critical tone', () => {
    act(() => {
      root.render(<Banner tone="critical">Ingest halted</Banner>);
    });

    const banner = container.querySelector('div.ui-banner.is-critical');
    expect(banner?.getAttribute('role')).toBe('alert');
  });

  it.each([
    'neutral',
    'info',
    'success',
    'warning',
  ] as const)('announces the %s tone as a status', (tone) => {
    act(() => {
      root.render(<Banner tone={tone}>notice</Banner>);
    });

    const banner = container.querySelector(`div.ui-banner.is-${tone}`);
    expect(banner?.getAttribute('role')).toBe('status');
  });
});
