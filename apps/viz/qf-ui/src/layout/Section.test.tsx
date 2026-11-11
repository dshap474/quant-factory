/**
 * Structural tests for the shared Section primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/layout/Section.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Section } from './Section';

const SECTION_CSS = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), 'Section.css'),
  'utf8',
);

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Section', () => {
  it('renders children without a heading when no title is given', () => {
    expect(renderToStaticMarkup(<Section>body</Section>)).toBe(
      '<section class="ui-section">body</section>',
    );
  });

  it('renders the heading only when a title is given', () => {
    const html = renderToStaticMarkup(<Section title="Recent">body</Section>);

    expect(html).toContain('<h2 class="section-heading">Recent</h2>');
    expect(html).toContain('body');
  });

  it('places actions beside the heading in one header row', () => {
    const html = renderToStaticMarkup(
      <Section title="Matrix" actions={<span>switch</span>}>
        body
      </Section>,
    );

    expect(html).toContain(
      '<div class="ui-section-header"><h2 class="section-heading">Matrix</h2><span>switch</span></div>',
    );
  });

  it('keeps ui-section while merging a caller className', () => {
    // The uniform stacked gap lives on `.ui-section + .ui-section`, so a caller
    // className must never replace the recipe class.
    expect(renderToStaticMarkup(<Section className="min-w-0">body</Section>)).toContain(
      'class="ui-section min-w-0"',
    );
  });

  it('neutralises the sibling gap inside grid and flex parents', () => {
    // `.ui-section + .ui-section` is flow-layout rhythm. Inside a grid it also
    // matches siblings in different COLUMNS, pushing the second column down;
    // inside a flex row it doubles the parent's own gap. Both parents must be
    // opted out by class, since CSS cannot query a parent's `display`.
    const neutraliser = SECTION_CSS.slice(SECTION_CSS.indexOf(':is('));

    for (const parent of [
      '.grid',
      '.flex',
      '.ui-grid',
      '.ui-chart-grid',
      '.ui-stat-grid',
      '.ui-split-row',
      '.ui-toolbar',
    ]) {
      expect(neutraliser).toContain(parent);
    }

    expect(neutraliser).toContain('> .ui-section');
    expect(neutraliser).toMatch(/margin-top:\s*0/);
  });
});
