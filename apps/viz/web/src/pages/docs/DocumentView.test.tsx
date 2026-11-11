/**
 * State-presentation tests for the shared document view.
 *
 * USAGE:
 *   pnpm test -- src/pages/docs/DocumentView.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { DocPage } from '@/lib/api/docs';
import { DocumentView } from './DocumentView';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const PAGE: DocPage = {
  path: 'packages/data/README.md',
  title: 'Data',
  markdown: '# Data',
  modified: null,
  generated: false,
};

function renderView(overrides: Partial<Parameters<typeof DocumentView>[0]> = {}): string {
  return renderToStaticMarkup(
    <DocumentView
      page={undefined}
      isLoading={false}
      error={null}
      onRetry={() => undefined}
      emptyTitle="No document selected"
      {...overrides}
    />,
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DocumentView', () => {
  it('renders the shared geometry-stable loading state before every other state', () => {
    const markup = renderView({ isLoading: true, error: new Error('stale error'), page: PAGE });

    expect(markup).toContain('aria-label="Loading content"');
    expect(markup).not.toContain('stale error');
    expect(markup).not.toContain('<article');
  });

  it('renders shared error and empty presentations', () => {
    const errorMarkup = renderView({ error: new Error('Document unavailable') });
    const emptyMarkup = renderView({ emptyHint: 'Choose a file.' });

    expect(errorMarkup).toContain('role="alert"');
    expect(errorMarkup).toContain('Document unavailable');
    expect(errorMarkup).toContain('Retry');
    expect(emptyMarkup).toContain('No document selected');
    expect(emptyMarkup).toContain('Choose a file.');
  });

  it('forwards reader-local markdown presentation without owning link rules', () => {
    const markup = renderView({ page: PAGE, markdownClassName: 'research-doc-prose' });

    expect(markup).toContain('<article');
    expect(markup).toContain('class="prose-dark prose-measure research-doc-prose"');
  });
});
