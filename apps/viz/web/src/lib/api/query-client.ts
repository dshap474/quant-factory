/**
 * Shared TanStack Query client for the React viz SPA.
 *
 * USAGE:
 *   import { createAppQueryClient } from './query-client';
 *   <QueryClientProvider client={createAppQueryClient()}>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './errors';

// --------------------------------------------------------------------------- #
// Factory
// --------------------------------------------------------------------------- #

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Domain hooks set an explicit staleTime; anything without one is always stale.
        staleTime: 0,
        // Retry once on transport/5xx only — not 4xx / client parse failures.
        retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status < 500),
        refetchOnWindowFocus: false,
      },
    },
  });
}
