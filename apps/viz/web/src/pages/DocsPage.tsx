/**
 * Package docs viewer — docs navigator + sanitized markdown body.
 *
 * USAGE:
 *   Routed at /docs?doc=<path>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useSearchParams } from 'react-router';
import { useDocPage, useDocsTree } from '@/lib/api/docs';
import { isLoadingData, PageHeader, QueryState, SectionWorkspace } from '@/ui';

import { DocsNavigator } from './docs/DocsNavigator';
import { DocumentView } from './docs/DocumentView';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DocsPage() {
  const [searchParams] = useSearchParams();
  const treeQuery = useDocsTree();
  const tree = treeQuery.data;
  const requestedPath =
    searchParams.get('doc') ?? tree?.default_path ?? tree?.root.children?.[0]?.path ?? '';
  const pageQuery = useDocPage(requestedPath);
  const selectedPath = pageQuery.data?.path ?? requestedPath;

  // The workspace content pane owns the scrollbar; `docs-workspace` is the route smoke
  // test's hook and carries no styles.
  return (
    <>
      {tree ? null : <PageHeader title="Docs" subtitle="Package documentation" />}

      <QueryState query={treeQuery} skeleton="line">
        {tree ? (
          <SectionWorkspace
            navigator={
              <DocsNavigator tree={tree.root.children ?? []} selectedPath={selectedPath} />
            }
            className="docs-workspace"
          >
            <PageHeader
              title={pageQuery.data?.title ?? selectedPath.split('/').at(-1) ?? 'Docs'}
              subtitle={selectedPath || 'Select a document from the package tree.'}
            />
            <section aria-live="polite">
              <DocumentView
                page={pageQuery.data}
                isLoading={isLoadingData(pageQuery)}
                error={pageQuery.error}
                onRetry={() => {
                  void pageQuery.refetch();
                }}
                emptyTitle="No document selected"
              />
            </section>
          </SectionWorkspace>
        ) : null}
      </QueryState>
    </>
  );
}
