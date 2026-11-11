/**
 * Alignment contract for the shared empty-state box.
 *
 * USAGE:
 *   pnpm exec vitest run src/state/EmptyState.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import { EmptyState } from './EmptyState';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

it('centres its text only when asked, never carrying both alignments', () => {
  const centered = renderToStaticMarkup(<EmptyState align="center" title="No rows" />);
  expect(centered).toContain('text-center');
  expect(centered).not.toContain('text-left');

  const start = renderToStaticMarkup(<EmptyState title="No rows" />);
  expect(start).toContain('text-left');
  expect(start).not.toContain('text-center');
});
