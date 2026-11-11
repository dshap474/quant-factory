/**
 * Structural tests for the shared Surface primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Surface.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Surface } from './Surface';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Surface', () => {
  it('renders a padded bordered card by default', () => {
    expect(renderToStaticMarkup(<Surface>x</Surface>)).toBe('<div class="ui-surface p-4">x</div>');
  });

  it('renders the panel variant on any element and forwards attributes', () => {
    expect(
      renderToStaticMarkup(
        <Surface as="section" variant="panel" padding="none" aria-label="IC matrix">
          x
        </Surface>,
      ),
    ).toBe('<section class="ui-surface ui-surface-panel" aria-label="IC matrix">x</section>');
  });

  it('renders the inset variant, clips on request, and merges className', () => {
    expect(
      renderToStaticMarkup(
        <Surface variant="inset" clip className="mt-2">
          x
        </Surface>,
      ),
    ).toBe('<div class="ui-surface ui-surface-inset ui-surface-clip p-4 mt-2">x</div>');
  });

  it('renders a tinted gutter panel with only the end rule and forwards aria-labelledby', () => {
    const markup = renderToStaticMarkup(
      <Surface
        as="section"
        variant="panel"
        padding="gutter"
        rules="block-end"
        tinted
        aria-labelledby="x"
      >
        y
      </Surface>,
    );

    expect(markup).toContain(
      'class="ui-surface ui-surface-panel is-rules-block-end is-tinted ui-surface-gutter"',
    );
    expect(markup).not.toMatch(/\bp-[346]\b/);
    expect(markup).toContain('aria-labelledby="x"');
  });
});
