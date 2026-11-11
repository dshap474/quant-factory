/**
 * Read and write a single URL query parameter as component state.
 *
 * The URL stays the source of truth, so back/forward and deep links keep
 * working; `defaultValue` is returned when the key is absent and is never
 * written into the URL on its own. The params come from the host router through
 * the qf-ui router adapter (`QfRouterProvider`), or the History API without one.
 *
 * USAGE:
 *   const [view, setView] = useSearchParamState('view', 'live');
 *   const [day, setDay] = useSearchParamState('day', '', { replace: true });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback } from 'react';

import { useQfRouter } from './RouterAdapter';

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export interface SearchParamStateOptions {
  /** Replace the history entry instead of pushing a new one. Defaults to false. */
  replace?: boolean;
}

export type SetSearchParamState = (value: string, options?: SearchParamStateOptions) => void;

export function useSearchParamState(
  key: string,
  defaultValue = '',
  options: SearchParamStateOptions = {},
): [string, SetSearchParamState] {
  const { replace: defaultReplace = false } = options;
  const { useSearchParams } = useQfRouter();
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? defaultValue;

  const setValue = useCallback<SetSearchParamState>(
    (next, callOptions) => {
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          params.set(key, next);
          return params;
        },
        { replace: callOptions?.replace ?? defaultReplace },
      );
    },
    [defaultReplace, key, setSearchParams],
  );

  return [value, setValue];
}
