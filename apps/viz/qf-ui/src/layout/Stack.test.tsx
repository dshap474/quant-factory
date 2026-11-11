/**
 * Structural tests for the shared Stack layout.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/Stack.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Stack } from './Stack';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Stack', () => {
  it('renders a vertical flex column with the default gap', () => {
    expect(renderToStaticMarkup(<Stack>x</Stack>)).toBe(
      '<div class="flex flex-col gap-[var(--gap-heading)]">x</div>',
    );
  });

  it('applies the gap preset and merges className', () => {
    expect(
      renderToStaticMarkup(
        <Stack gap="xs" className="min-w-0">
          x
        </Stack>,
      ),
    ).toBe('<div class="flex flex-col gap-1 min-w-0">x</div>');
  });
  it('supports the none gap', () => {
    expect(renderToStaticMarkup(<Stack gap="none">x</Stack>)).toBe(
      '<div class="flex flex-col gap-0">x</div>',
    );
  });
});
