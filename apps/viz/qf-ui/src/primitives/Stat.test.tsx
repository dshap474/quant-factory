/**
 * Structural tests for the shared Stat primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Stat.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Stat } from './Stat';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Stat', () => {
  it('renders a label over a value', () => {
    expect(renderToStaticMarkup(<Stat label="AUC" value="91%" />)).toBe(
      '<div class="min-w-0">' +
        '<div class="font-medium text-muted-foreground text-caption">AUC</div>' +
        '<div class="font-semibold tabular-nums text-foreground text-section">91%</div></div>',
    );
  });

  it('applies size, mono, tone, and className', () => {
    const markup = renderToStaticMarkup(
      <Stat label="Cost" value="$12" size="sm" mono tone="success" className="shrink-0" />,
    );

    expect(markup).toContain('<div class="min-w-0 shrink-0">');
    expect(markup).toContain('text-muted-foreground text-caption');
    expect(markup).toContain('font-semibold tabular-nums text-positive text-body font-mono');
  });
});
