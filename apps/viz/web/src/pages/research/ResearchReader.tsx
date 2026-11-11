/**
 * One packages/research markdown file, without a page header: relative links stay inside the
 * research readers (researchDocRoute) and relative images are served by /api/research/asset.
 *
 * The document sits in the qf-ui Reader frame: a sticky section nav built from its headings,
 * a fixed reading column, and corpus citations set as muted <cite> references.
 *
 * USAGE:
 *   <ResearchReader docPath="corpus/wiki/topic.md" />
 *   <ResearchReader docPath="docs/x.md" meta={[{ label: 'Folder', value: 'docs' }]} actions={<GraphLink />} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useState } from 'react';
import { encodePath } from '@/lib/api/paths';
import { researchDocRoute, useResearchDoc } from '@/lib/api/research';
import { useDocumentTitle } from '@/lib/shared/lib/page-title';
import { type ProseLayout, Reader, type ReaderMetaItem, type ReaderPagerProps } from '@/ui';
import { DocumentView } from '../docs/DocumentView';
import type { DocumentSection, MarkdownLinkOptions } from '../docs/markdown';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Markdown sources percent-encode spaces; decode before re-encoding a URL. */
export function decodePathSafely(path: string): string {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

// Module-level so <SanitizedMarkdown> does not re-render on every parent pass.
const RESEARCH_LINKS: MarkdownLinkOptions = {
  toHref: (path) => researchDocRoute(decodePathSafely(path)),
  toAssetSrc: (path) => `/api/research/asset/${encodePath(decodePathSafely(path))}`,
  isCitation: (href) => href.startsWith('/corpus/sources/'),
};

// --------------------------------------------------------------------------- #
// Reader
// --------------------------------------------------------------------------- #

/** One research markdown file in the reading frame, without a page header. */
export function ResearchReader({
  docPath,
  lede,
  meta,
  actions,
  layout,
  highlight,
  pager,
  children,
}: {
  docPath: string;
  lede?: ReactNode;
  meta?: readonly ReaderMetaItem[];
  actions?: ReactNode;
  /** `index` sets a back-of-book index in columns. */
  layout?: ProseLayout;
  /** A search whose words are marked in the text, the first brought into view. */
  highlight?: string;
  /** Previous and next documents in a sequence (a book's chapters). */
  pager?: Omit<ReaderPagerProps, 'className'>;
  /** Rendered in the reading column after the document. */
  children?: ReactNode;
}) {
  const docQuery = useResearchDoc(docPath);
  useDocumentTitle(docQuery.data?.title);
  const [sections, setSections] = useState<DocumentSection[]>([]);
  // The section workspace content pane owns the scrollbar; the reader adds no wrapper.
  return (
    <Reader
      title={docQuery.data?.title}
      lede={lede}
      meta={meta}
      sections={sections}
      actions={actions}
      pager={pager}
    >
      <section aria-live="polite">
        <DocumentView
          page={docQuery.data}
          isLoading={docQuery.isLoading}
          error={docQuery.error}
          onRetry={() => {
            void docQuery.refetch();
          }}
          emptyTitle="Document is empty"
          links={RESEARCH_LINKS}
          readerMarkup
          layout={layout}
          highlight={highlight}
          onSections={setSections}
        />
      </section>
      {children}
    </Reader>
  );
}
