/**
 * Shared loading, error, empty, and sanitized-markdown presentation for document readers.
 *
 * USAGE:
 *   <DocumentView page={page} isLoading={isLoading} error={error} onRetry={refetch}
 *     emptyTitle="No document selected" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { DocPage } from '@/lib/api/docs';
import { EmptyState, ErrorPanel, LoadingSkeleton, type ProseLayout } from '@/ui';

import type { DocumentSection, MarkdownLinkOptions } from './markdown';
import { SanitizedMarkdown } from './SanitizedMarkdown';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DocumentViewProps {
  page: DocPage | undefined;
  isLoading: boolean;
  error: Error | null;
  onRetry?: () => void;
  emptyTitle: string;
  emptyHint?: string;
  links?: MarkdownLinkOptions;
  markdownClassName?: string;
  /** Reader-frame markup: numbered headings, anchors, references, figures. */
  readerMarkup?: boolean;
  /** `index` sets a back-of-book index in columns. */
  layout?: ProseLayout;
  /** A search whose words are marked in the text. */
  highlight?: string;
  onSections?: (sections: DocumentSection[]) => void;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DocumentView({
  page,
  isLoading,
  error,
  onRetry,
  emptyTitle,
  emptyHint,
  links,
  markdownClassName,
  readerMarkup,
  layout,
  highlight,
  onSections,
}: DocumentViewProps) {
  if (isLoading) return <LoadingSkeleton count={8} />;
  if (error && !page) return <ErrorPanel message={error.message} onRetry={onRetry} />;
  if (!page) return <EmptyState title={emptyTitle} hint={emptyHint} />;

  return (
    <SanitizedMarkdown
      page={page}
      links={links}
      className={markdownClassName}
      hideLeadingTitle
      readerMarkup={readerMarkup}
      layout={layout}
      highlight={highlight}
      onSections={onSections}
    />
  );
}
