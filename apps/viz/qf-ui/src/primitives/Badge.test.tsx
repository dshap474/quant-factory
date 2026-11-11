/**
 * Structural tests for Badge tone classes.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Badge.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { TONES } from '../lib/tone';
import { Badge } from './Badge';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Badge', () => {
  it.each(TONES)('colours the %s badge from the tone tokens', (tone) => {
    const markup = renderToStaticMarkup(<Badge tone={tone}>x</Badge>);

    expect(markup).toContain(`text-tone-${tone}`);
    expect(markup).toContain(`border-tone-${tone}-border`);
  });

  it('defaults to neutral and drops tone colour for the ghost variant', () => {
    expect(renderToStaticMarkup(<Badge>x</Badge>)).toContain('text-tone-neutral');
    const ghost = renderToStaticMarkup(
      <Badge tone="critical" variant="ghost">
        x
      </Badge>,
    );
    expect(ghost).not.toContain('text-tone-critical');
    expect(ghost).toContain('border-transparent');
    expect(ghost).not.toContain('bg-tone-');
  });

  it.each(TONES)('fills the solid %s badge with its tone surface', (tone) => {
    const markup = renderToStaticMarkup(<Badge tone={tone}>x</Badge>);
    expect(markup).toContain('ui-badge');
    expect(markup).toContain(`bg-tone-${tone}-surface`);
  });
});
