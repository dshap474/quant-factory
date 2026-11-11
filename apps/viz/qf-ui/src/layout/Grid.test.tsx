/**
 * Structural tests for the shared Grid layout.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/Grid.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Grid } from './Grid';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Grid', () => {
  it('renders class-driven presets instead of inline styles', () => {
    const markup = renderToStaticMarkup(<Grid>x</Grid>);

    expect(markup).toBe('<div class="ui-grid is-min-md is-gap-block">x</div>');
    expect(markup).not.toContain('style=');
  });

  it('applies width and gap presets and merges className', () => {
    expect(
      renderToStaticMarkup(
        <Grid minItemWidth="sm" gap="stack" className="min-w-0">
          x
        </Grid>,
      ),
    ).toBe('<div class="ui-grid is-min-sm is-gap-stack min-w-0">x</div>');
  });
});
