/**
 * Markdown link/image rewriting tests for the docs and research readers.
 *
 * USAGE:
 *   pnpm test -- src/pages/docs/markdown.test.ts
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import type { DocPage } from '@/lib/api/docs';
import { encodePath } from '@/lib/api/paths';
import { type MarkdownLinkOptions, renderMarkdown } from './markdown';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const DOC_PATH = 'corpus/sources/books/example-book.md';

const MARKDOWN = [
  '[sibling](./nested/other.md)',
  '',
  '![diagram](assets/diagram.png)',
  '',
  '[external](https://example.com/x)',
].join('\n');

function docPage(markdown: string, path: string): DocPage {
  return { path, title: 'Example book', markdown, modified: null, generated: false };
}

const RESEARCH_LINKS: MarkdownLinkOptions = {
  toHref: (path) => `/research/doc/${encodePath(path)}`,
  toAssetSrc: (path) => `/api/research/asset/${encodePath(path)}`,
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('renderMarkdown', () => {
  it('keeps the default docs behaviour when no links option is given', () => {
    const html = renderMarkdown(docPage(MARKDOWN, DOC_PATH));

    expect(html).toContain(
      `href="/docs?doc=${encodeURIComponent('corpus/sources/books/nested/other.md')}"`,
    );
    // Images are untouched without `toAssetSrc`.
    expect(html).toContain('src="assets/diagram.png"');
    expect(html).not.toContain('/api/research/asset/');
  });

  it('routes relative links and images through the research reader', () => {
    const html = renderMarkdown(docPage(MARKDOWN, DOC_PATH), RESEARCH_LINKS);

    expect(html).toContain('href="/research/doc/corpus/sources/books/nested/other.md"');
    expect(html).toContain('src="/api/research/asset/corpus/sources/books/assets/diagram.png"');
    expect(html).not.toContain('/docs?doc=');
  });

  it('leaves absolute and external references alone', () => {
    const html = renderMarkdown(docPage(MARKDOWN, DOC_PATH), RESEARCH_LINKS);

    expect(html).toContain('href="https://example.com/x"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
