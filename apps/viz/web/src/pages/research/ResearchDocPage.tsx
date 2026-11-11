/**
 * Read-only markdown reader for packages/research: the docs tree under /research/doc, sandbox
 * and source docs under /sandbox/doc, and corpus notes and texts under /corpus.
 *
 * USAGE:
 *   <ResearchDocPage />                     // /research/doc/docs/x.md, /sandbox/doc/sandbox/x.md
 *   <ResearchDocPage prefix="corpus/sources/" />   // /corpus/sources/books/Name/text.md
 *
 * The splat (after `prefix`) is the packages/research-relative markdown path. A path that
 * belongs to another section redirects there, so old /research/doc/corpus/... links still
 * open. Nothing here is editable.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { Navigate, useLocation, useParams } from 'react-router';
import { researchDocRoute, useResearchDoc } from '@/lib/api/research';
import { PageHeader } from '@/ui';
import { DocumentView } from '../docs/DocumentView';
import { decodePathSafely, ResearchReader } from './ResearchReader';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ResearchDocPage({ prefix = '', tabs }: { prefix?: string; tabs?: ReactNode }) {
  const splat = useParams()['*'] ?? '';
  const { pathname, hash } = useLocation();
  const docPath = splat ? `${prefix}${splat}` : '';
  const docQuery = useResearchDoc(docPath);

  const home = researchDocRoute(docPath);
  if (docPath && decodePathSafely(pathname) !== decodePathSafely(home)) {
    return <Navigate to={{ pathname: home, hash }} replace />;
  }

  const segments = docPath.split('/').filter(Boolean);
  const title = docQuery.data?.title ?? segments.at(-1) ?? 'Document';

  if (!docPath) {
    return (
      <>
        <PageHeader title="Document" subtitle="Pick a file from the tree." tabs={tabs} />
        <DocumentView
          page={undefined}
          isLoading={false}
          error={null}
          emptyTitle="No document selected"
          emptyHint="Pick a file from the tree."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={title}
        subtitle={segments.map((segment) => segment.replace(/\.md$/i, '')).join(' / ')}
        tabs={tabs}
      />
      <ResearchReader
        docPath={docPath}
        meta={[
          {
            label: 'Folder',
            value: segments
              .slice(0, -1)
              .map((segment) => decodePathSafely(segment))
              .join(' / '),
          },
        ]}
      />
    </>
  );
}
