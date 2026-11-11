/**
 * PageShell class contract: default width wrapper and the bounded fill column.
 *
 * USAGE:
 *   pnpm exec vitest run src/frame/PageShell.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { PageShell } from './PageShell';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function host(ui: ReactNode): HTMLDivElement {
  const node = document.createElement('div');
  node.innerHTML = renderToStaticMarkup(ui);
  return node;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('PageShell', () => {
  it('renders the default width wrapper without the fill modifier', () => {
    const node = host(<PageShell>x</PageShell>);
    const shell = node.querySelector('div.page-shell.max-w-\\[1400px\\]');
    expect(shell).not.toBeNull();
    expect(shell?.classList.contains('is-fill')).toBe(false);
  });

  it('renders a bounded fill column with the caller classes', () => {
    const node = host(
      <PageShell fill maxWidth="full" className="min-h-0">
        x
      </PageShell>,
    );
    const shell = node.querySelector('div.page-shell');
    expect(shell?.getAttribute('class')).toBe('page-shell is-fill max-w-none min-h-0');
  });
});
