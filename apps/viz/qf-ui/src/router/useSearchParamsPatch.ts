/**
 * Write several URL query parameters in one history entry. A key set to a string
 * is written; a key set to `null`, `undefined` or `''` is removed, so cleared
 * filters leave no empty `?key=` behind. Keys not named are kept.
 *
 * USAGE:
 *   const patchParams = useSearchParamsPatch();
 *   patchParams({ status: 'failed', page: null });
 *   patchParams({ run: runId }, { replace: true });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback } from 'react';

import { useQfRouter } from './RouterAdapter';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type SearchParamsPatch = Readonly<Record<string, string | null | undefined>>;

export interface SearchParamsPatchOptions {
  /** Replace the history entry instead of pushing a new one. Defaults to false. */
  replace?: boolean;
}

export type PatchSearchParams = (
  patch: SearchParamsPatch,
  options?: SearchParamsPatchOptions,
) => void;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** A copy of `current` with `patch` applied: strings set, empty or missing values delete. */
export function applySearchParamsPatch(
  current: URLSearchParams,
  patch: SearchParamsPatch,
): URLSearchParams {
  const params = new URLSearchParams(current);
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === undefined || value === '') params.delete(key);
    else params.set(key, value);
  }
  return params;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useSearchParamsPatch(): PatchSearchParams {
  const { useSearchParams } = useQfRouter();
  const [, setSearchParams] = useSearchParams();
  return useCallback<PatchSearchParams>(
    (patch, options) => {
      setSearchParams((current) => applySearchParamsPatch(current, patch), {
        replace: options?.replace ?? false,
      });
    },
    [setSearchParams],
  );
}
