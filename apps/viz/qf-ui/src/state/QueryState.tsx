/**
 * Shared loading / error / empty gates for query-backed regions.
 *
 * Takes the query objects themselves (structurally; qf-ui never imports a query
 * library) so every region applies one rule: a skeleton while there is no data
 * for the current parameters (first load, placeholder data from previous
 * parameters, retry), an error only when there is nothing to show, an empty
 * state for a disabled query or empty data, and the loaded content kept, under
 * a warning banner, when a refresh with the same parameters fails.
 *
 * USAGE:
 *   <QueryState query={runsQuery} skeleton="table" isEmpty={runs.length === 0} emptyTitle="No runs">
 *     {children}
 *   </QueryState>
 *   <QueryState query={[sessionsQuery, sessionQuery]} skeleton="chart">{children}</QueryState>
 *   if (isLoadingData(query)) return <LoadingSkeleton variant="chart" />;
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { Banner } from './Banner';
import { EmptyState } from './EmptyState';
import { ErrorPanel } from './ErrorPanel';
import { LoadingSkeleton } from './LoadingSkeleton';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** The query fields the loading rule reads (TanStack Query results satisfy it). */
export interface QueryLike {
  data: unknown;
  error: Error | null;
  isFetching: boolean;
  isPlaceholderData: boolean;
  refetch: () => unknown;
}

export interface QueryStateProps {
  query: QueryLike | readonly QueryLike[];
  isEmpty?: boolean;
  emptyTitle?: string;
  emptyHint?: string | undefined;
  /** Defaults to refetching every query. */
  onRetry?: () => void;
  skeleton?: 'card' | 'chart' | 'line' | 'table';
  /** Skeleton repeat count. Default 4. */
  count?: number;
  label?: string | undefined;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Rule
// --------------------------------------------------------------------------- #

/** True while a query has no data for its current parameters but is getting it. */
export function isLoadingData(query: QueryLike): boolean {
  return query.isPlaceholderData || (query.data === undefined && query.isFetching);
}

function hasData(query: QueryLike): boolean {
  return query.data !== undefined && !query.isPlaceholderData;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function QueryState({
  query,
  isEmpty = false,
  emptyTitle = 'Nothing here',
  emptyHint,
  onRetry,
  skeleton = 'card',
  count = 4,
  label,
  children,
}: QueryStateProps) {
  const queries: readonly QueryLike[] = Array.isArray(query) ? query : [query as QueryLike];
  const retry =
    onRetry ??
    (() => {
      for (const q of queries) void q.refetch();
    });

  if (queries.some(isLoadingData)) {
    return <LoadingSkeleton variant={skeleton} count={count} {...(label ? { label } : {})} />;
  }
  const failed = queries.find((q) => q.error && !hasData(q));
  if (failed?.error) return <ErrorPanel message={failed.error.message} onRetry={retry} />;
  if (isEmpty || !queries.every(hasData)) {
    return <EmptyState title={emptyTitle} hint={emptyHint} />;
  }
  const refreshError = queries.find((q) => q.error)?.error;
  return (
    <>
      {refreshError ? (
        <Banner tone="warning">
          Refresh failed, showing the last loaded data: {refreshError.message}
        </Banner>
      ) : null}
      {children}
    </>
  );
}
