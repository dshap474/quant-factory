/**
 * Structural tests for StatGrid and StatItem.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/StatGrid.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StatGrid, StatItem } from './StatGrid';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('StatGrid', () => {
  it('renders a definition list of labelled values', () => {
    const markup = renderToStaticMarkup(
      <StatGrid aria-label="Snapshot">
        <StatItem label="Published" value="2026-09-09" />
      </StatGrid>,
    );

    expect(markup).toBe(
      '<dl class="ui-stat-grid is-grid" aria-label="Snapshot">' +
        '<div class="ui-stat-item"><dt class="ui-stat-label">Published</dt>' +
        '<dd class="ui-stat-value">2026-09-09</dd></div></dl>',
    );
  });

  it('applies the strip variant with a fixed column count and merges className', () => {
    const markup = renderToStaticMarkup(
      <StatGrid variant="strip" columns={4} className="mb-6">
        <StatItem label="Canonical" value="v002" />
      </StatGrid>,
    );

    expect(markup).toContain('<dl class="ui-stat-grid is-strip is-cols-4 mb-6">');
  });

  it('frames the strip when boxed', () => {
    expect(
      renderToStaticMarkup(
        <StatGrid variant="strip" columns={4} boxed>
          <StatItem label="Canonical" value="v002" />
        </StatGrid>,
      ),
    ).toContain('<dl class="ui-stat-grid is-strip is-cols-4 is-boxed">');
  });

  it('omits the boxed class by default', () => {
    expect(
      renderToStaticMarkup(
        <StatGrid variant="strip">
          <StatItem label="Canonical" value="v002" />
        </StatGrid>,
      ),
    ).not.toContain('is-boxed');
  });

  it('applies the inline variant', () => {
    const markup = renderToStaticMarkup(
      <StatGrid variant="inline" aria-label="Summary">
        <StatItem label="Close" value="4.50%" />
      </StatGrid>,
    );

    expect(markup).toContain('<dl class="ui-stat-grid is-inline" aria-label="Summary">');
    expect(markup).toContain('<div class="ui-stat-item">');
  });

  it('applies the rows variant', () => {
    expect(
      renderToStaticMarkup(
        <StatGrid variant="rows">
          <StatItem label="Task" value="classify" />
        </StatGrid>,
      ),
    ).toContain('<dl class="ui-stat-grid is-rows">');
  });
});

describe('StatItem', () => {
  it('tones the value and forwards item attributes', () => {
    const markup = renderToStaticMarkup(
      <StatGrid>
        <StatItem label="Fees" value="$12" tone="critical" title="net of fees" />
        <StatItem label="Fill" value="98%" tone="success" className="col-span-2" />
      </StatGrid>,
    );

    expect(markup).toContain('<div class="ui-stat-item" title="net of fees">');
    expect(markup).toContain('<dd class="ui-stat-value is-critical">$12</dd>');
    expect(markup).toContain('<div class="ui-stat-item col-span-2">');
    expect(markup).toContain('<dd class="ui-stat-value is-success">98%</dd>');
  });

  it('renders a toned delta inside the value cell only when given', () => {
    const withDelta = renderToStaticMarkup(
      <StatGrid variant="inline">
        <StatItem label="Close" value="4.50%" delta="+20.0 bp" deltaTone="positive" />
      </StatGrid>,
    );
    const withoutDelta = renderToStaticMarkup(
      <StatGrid variant="inline">
        <StatItem label="Close" value="4.50%" />
      </StatGrid>,
    );

    expect(withDelta).toContain(
      '<dd class="ui-stat-value">4.50%<span class="ui-stat-delta is-positive">+20.0 bp</span></dd>',
    );
    expect(withoutDelta).not.toContain('ui-stat-delta');
  });
});
