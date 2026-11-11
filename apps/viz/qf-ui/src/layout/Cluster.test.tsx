/**
 * Structural tests for the shared Cluster layout.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/Cluster.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Cluster } from './Cluster';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Cluster', () => {
  it('renders a wrapping row with the default gap and alignment', () => {
    expect(renderToStaticMarkup(<Cluster>x</Cluster>)).toBe(
      '<div class="flex flex-wrap items-center gap-[var(--gap-heading)] justify-start">x</div>',
    );
  });

  it('applies gap and justify presets and merges className', () => {
    expect(
      renderToStaticMarkup(
        <Cluster gap="block" justify="between" className="min-w-0">
          x
        </Cluster>,
      ),
    ).toBe(
      '<div class="flex flex-wrap items-center gap-[var(--gap-block)] justify-between min-w-0">x</div>',
    );
  });
});
