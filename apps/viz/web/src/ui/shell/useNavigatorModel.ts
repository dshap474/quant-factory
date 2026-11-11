/**
 * TanStack Query binding for qf-ui's `useTreeNavigatorState`: the two-level
 * navigator (families → versions) whose children load on demand through
 * `useQueries`. Expand and search state live in qf-ui; this hook only supplies the
 * child loader.
 *
 * USAGE:
 *   const model = useNavigatorModel({
 *     families,
 *     familyId: (family) => family.signal_family,
 *     currentId: params.family,
 *     familyMatches: (family, query) => family.signal_family.toLowerCase().includes(query),
 *     childMatches: (version, query) => version.memory_version.toLowerCase().includes(query),
 *     childrenQueryKey: (id) => signalKeys.researchVersions(id),
 *     loadChildren: (id, signal) => listSignalResearchVersions(id, signal),
 *     staleTime: STALE.list,
 *   });
 *   const { children, loading, error } = model.childrenOf(id);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type TreeNavigatorChildren,
  type TreeNavigatorState,
  type TreeNavigatorStateOptions,
  useTreeNavigatorState,
} from '@quant-factory/qf-ui';
import { type QueryKey, type UseQueryOptions, useQueries } from '@tanstack/react-query';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface NavigatorModelOptions<Family, Child>
  extends Omit<TreeNavigatorStateOptions<Family, Child>, 'useChildren'> {
  childrenQueryKey: (id: string) => QueryKey;
  loadChildren: (id: string, signal?: AbortSignal) => Promise<Child[]>;
  staleTime?: number;
}

export type NavigatorChildren<Child> = TreeNavigatorChildren<Child>;

export type NavigatorModel<Family, Child> = TreeNavigatorState<Family, Child>;

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useNavigatorModel<Family, Child>({
  childrenQueryKey,
  loadChildren,
  staleTime,
  ...options
}: NavigatorModelOptions<Family, Child>): NavigatorModel<Family, Child> {
  const useChildren = (ids: string[]): Record<string, NavigatorChildren<Child>> => {
    const results = useQueries({
      queries: ids.map(
        (id): UseQueryOptions<Child[], Error, Child[], QueryKey> => ({
          queryKey: childrenQueryKey(id),
          queryFn: ({ signal }) => loadChildren(id, signal),
          staleTime,
          enabled: Boolean(id),
        }),
      ),
    });
    const byId: Record<string, NavigatorChildren<Child>> = {};
    ids.forEach((id, index) => {
      const result = results[index];
      byId[id] = {
        children: result?.data ?? [],
        loading: Boolean(result?.isLoading),
        error: result?.error?.message ?? null,
      };
    });
    return byId;
  };

  return useTreeNavigatorState({ ...options, useChildren });
}
