/**
 * Research home: every markdown document under packages/research/docs.
 *
 * USAGE:
 *   Routed at /research
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { type ResearchNavNode, useResearchDocs } from '@/lib/api/research';
import { EmptyState, ErrorPanel, Link, LoadingSkeleton, PageHeader, Stack, Text } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function leaves(
  nodes: readonly ResearchNavNode[],
  trail: string[] = [],
): Array<[ResearchNavNode, string]> {
  return nodes.flatMap((node) =>
    node.kind === 'folder'
      ? leaves(node.children ?? [], [...trail, node.title])
      : [[node, trail.join(' / ')] as [ResearchNavNode, string]],
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ResearchPage() {
  const docs = useResearchDocs();
  const rows = leaves(docs.data?.nav ?? []);

  let body: ReactNode;
  if (docs.isLoading) body = <LoadingSkeleton count={6} />;
  else if (docs.error)
    body = <ErrorPanel message={docs.error.message} onRetry={() => void docs.refetch()} />;
  else if (rows.length === 0) body = <EmptyState title="No research documents" />;
  else
    body = (
      <Stack gap="heading">
        {rows.map(([node, folder]) => (
          <Stack key={node.id} gap="none">
            <Link to={node.route ?? '/research'}>{node.title}</Link>
            {folder ? (
              <Text variant="caption" tone="muted">
                {folder}
              </Text>
            ) : null}
          </Stack>
        ))}
      </Stack>
    );

  return (
    <>
      <PageHeader title="Research" subtitle="packages/research/docs" />
      {body}
    </>
  );
}
