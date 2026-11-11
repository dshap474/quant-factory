/**
 * Structural tests for the shared PageHeader rail.
 *
 * USAGE:
 *   pnpm exec vitest run src/frame/PageHeader.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { PageHeader } from './PageHeader';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('PageHeader', () => {
  it('renders only the title when nothing else is given', () => {
    const html = renderToStaticMarkup(<PageHeader title="Signals" />);

    expect(html).toContain('<h1>Signals</h1>');
    expect(html).not.toContain('page-header-subtitle');
    expect(html).not.toContain('page-header-actions');
    expect(html).not.toContain('page-header-badges');
  });

  it('renders badges on the title line and the subtitle underneath', () => {
    const html = renderToStaticMarkup(
      <PageHeader title="Signals" badges={<b>sealed</b>} subtitle="Sealed rounds" />,
    );

    expect(html).toContain(
      '<div class="page-header-title-line"><h1>Signals</h1><span class="page-header-badges"><b>sealed</b></span></div><div class="page-header-subtitle">Sealed rounds</div>',
    );
  });

  it('renders the subtitle and right slot when given', () => {
    const html = renderToStaticMarkup(
      <PageHeader title="Signals" subtitle="Sealed rounds" right={<i data-x="facts" />} />,
    );

    expect(html).toContain('<div class="page-header-subtitle">Sealed rounds</div>');
    expect(html).toContain('<div class="page-header-actions"><i data-x="facts"></i></div>');
  });

  it('merges a caller className onto the header', () => {
    expect(renderToStaticMarkup(<PageHeader title="Signals" className="is-terminal" />)).toContain(
      'class="page-header is-terminal"',
    );
  });
});
