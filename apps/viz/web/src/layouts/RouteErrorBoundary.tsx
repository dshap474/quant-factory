/**
 * Route-level error element: keeps a thrown render or a failed lazy chunk
 * inside the content pane instead of letting react-router replace the whole
 * shell with its default error screen.
 *
 * USAGE:
 *   { path: 'catalog', element: <CatalogPage />, errorElement: <RouteErrorBoundary /> }
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { isRouteErrorResponse, useRouteError } from 'react-router';
import { isChunkLoadError, reloadForStaleChunk } from '@/lib/chunk-reload';
import { EmptyState, ErrorPanel, LoadingSkeleton, PageHeader, PageShell } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function errorMessage(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    return `${error.status} ${error.statusText}`;
  }
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  return 'This page failed to render.';
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RouteErrorBoundary() {
  const error = useRouteError();

  if (isRouteErrorResponse(error) && error.status === 404) {
    return (
      <PageShell maxWidth="full">
        <PageHeader title="Page not found" subtitle="No page is registered at this address." />
        <EmptyState title="Page not found" hint="No page is registered at this address." />
      </PageShell>
    );
  }

  // A stale hashed chunk resolves itself on reload, so recover silently rather
  // than showing an error the operator cannot act on.
  if (isChunkLoadError(error) && reloadForStaleChunk()) {
    return (
      <PageShell maxWidth="full">
        <LoadingSkeleton variant="chart" />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="full">
      <PageHeader
        title="Something went wrong"
        subtitle="This page failed to load. The rest of the workspace is unaffected."
      />
      <ErrorPanel message={errorMessage(error)} onRetry={() => window.location.reload()} />
    </PageShell>
  );
}
