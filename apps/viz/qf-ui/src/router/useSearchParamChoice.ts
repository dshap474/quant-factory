/**
 * A URL query parameter constrained to a fixed set of choices. An absent, unknown
 * or disallowed value reads as `fallback`; `aliases` map retired values onto
 * current ones so old links keep working. Choosing `fallback` removes the key, so
 * the default view keeps a clean URL.
 *
 * USAGE:
 *   const [view, setView] = useSearchParamChoice('view', ['chart', 'table'], 'chart');
 *   const [tab, setTab] = useSearchParamChoice('tab', tabs, 'features', {
 *     aliases: { overview: 'features' },
 *   });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback } from 'react';

import { useQfRouter } from './RouterAdapter';
import { applySearchParamsPatch } from './useSearchParamsPatch';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SearchParamChoiceOptions<T extends string> {
  /** Retired values mapped onto current choices. */
  aliases?: Readonly<Record<string, T>>;
  /** Replace the history entry instead of pushing a new one. Defaults to false. */
  replace?: boolean;
}

export type SetSearchParamChoice<T extends string> = (
  value: T,
  options?: { replace?: boolean },
) => void;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** The choice a raw param value selects: aliased, then validated, else `fallback`. */
export function resolveSearchParamChoice<T extends string>(
  raw: string | null,
  choices: readonly T[],
  fallback: T,
  aliases?: Readonly<Record<string, T>>,
): T {
  if (raw === null) return fallback;
  const requested = aliases?.[raw] ?? raw;
  return choices.find((choice) => choice === requested) ?? fallback;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useSearchParamChoice<T extends string>(
  key: string,
  choices: readonly T[],
  fallback: T,
  options: SearchParamChoiceOptions<T> = {},
): [T, SetSearchParamChoice<T>] {
  const { aliases, replace: defaultReplace = false } = options;
  const { useSearchParams } = useQfRouter();
  const [searchParams, setSearchParams] = useSearchParams();
  const value = resolveSearchParamChoice(searchParams.get(key), choices, fallback, aliases);

  const setValue = useCallback<SetSearchParamChoice<T>>(
    (next, callOptions) => {
      setSearchParams(
        (current) => applySearchParamsPatch(current, { [key]: next === fallback ? null : next }),
        { replace: callOptions?.replace ?? defaultReplace },
      );
    },
    [defaultReplace, fallback, key, setSearchParams],
  );

  return [value, setValue];
}
