/**
 * Expand / search / lazy-children state for a two-level navigator (parents →
 * children). Expansion defaults open for the current parent, an active search
 * auto-expands the first visible parents, and children load on demand through a
 * host-supplied loader hook, so qf-ui never owns data fetching.
 *
 * `useChildren` is a hook: it receives the parent ids whose children are needed
 * (requested, current, and search-expanded, in that order) and returns their
 * children with loading and error state. It is called unconditionally on every
 * render, so pass a stable function.
 *
 * USAGE:
 *   const state = useTreeNavigatorState({
 *     families,
 *     familyId: (family) => family.name,
 *     currentId: params.family,
 *     familyMatches: (family, query) => family.name.toLowerCase().includes(query),
 *     childMatches: (version, query) => version.id.toLowerCase().includes(query),
 *     useChildren: useVersionsByFamily,
 *   });
 *   const { children, loading, error } = state.childrenOf(id);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TreeNavigatorChildren<Child> {
  children: Child[];
  loading: boolean;
  error: string | null;
}

/** Host loader hook: children (with loading/error) for each requested parent id. */
export type TreeNavigatorChildrenLoader<Child> = (
  ids: string[],
) => Record<string, TreeNavigatorChildren<Child>>;

export interface TreeNavigatorStateOptions<Family, Child> {
  families: Family[];
  familyId: (family: Family) => string;
  /** Family open by default and always loaded. */
  currentId?: string | null;
  /** Receives the normalized (trimmed, lower-cased) query. */
  familyMatches: (family: Family, query: string) => boolean;
  childMatches: (child: Child, query: string) => boolean;
  useChildren: TreeNavigatorChildrenLoader<Child>;
  sortChildren?: (left: Child, right: Child) => number;
  /** Visible families auto-expanded (and loaded) while searching. */
  searchExpandLimit?: number;
}

export interface TreeNavigatorState<Family, Child> {
  query: string;
  setQuery: (query: string) => void;
  queryNormalized: string;
  visibleFamilies: Family[];
  isExpanded: (id: string) => boolean;
  toggle: (id: string) => void;
  childrenOf: (id: string) => TreeNavigatorChildren<Child>;
  /** Whether a child row matches the active query (always true without one). */
  childVisible: (child: Child) => boolean;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

function emptyChildren<Child>(): TreeNavigatorChildren<Child> {
  return { children: [], loading: false, error: null };
}

export function useTreeNavigatorState<Family, Child>({
  families,
  familyId,
  currentId,
  familyMatches,
  childMatches,
  useChildren,
  sortChildren,
  searchExpandLimit = 8,
}: TreeNavigatorStateOptions<Family, Child>): TreeNavigatorState<Family, Child> {
  const current = currentId ?? null;
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    current ? { [current]: true } : {},
  );
  const [requested, setRequested] = useState<string[]>(() => (current ? [current] : []));
  const [query, setQuery] = useState('');
  const queryNormalized = query.trim().toLowerCase();

  const visibleFamilies = queryNormalized
    ? families.filter((family) => familyMatches(family, queryNormalized))
    : families;
  const searchExpanded = queryNormalized
    ? visibleFamilies.slice(0, searchExpandLimit).map(familyId)
    : [];

  const familiesToLoad = Array.from(
    new Set([...requested, ...(current ? [current] : []), ...searchExpanded]),
  );

  const loaded = useChildren(familiesToLoad);

  const childrenById: Record<string, TreeNavigatorChildren<Child>> = {};
  for (const id of familiesToLoad) {
    const result = loaded[id];
    const children = result ? [...result.children] : [];
    if (sortChildren) children.sort(sortChildren);
    childrenById[id] = {
      children,
      loading: Boolean(result?.loading),
      error: result?.error ?? null,
    };
  }

  const isExpanded = (id: string): boolean => {
    if (searchExpanded.includes(id)) return true;
    if (Object.hasOwn(expanded, id)) return Boolean(expanded[id]);
    return id === current;
  };

  const toggle = (id: string) => {
    setExpanded((previous) => {
      const open = Object.hasOwn(previous, id) ? Boolean(previous[id]) : id === current;
      return { ...previous, [id]: !open };
    });
    setRequested((previous) => (previous.includes(id) ? previous : [...previous, id]));
  };

  return {
    query,
    setQuery,
    queryNormalized,
    visibleFamilies,
    isExpanded,
    toggle,
    childrenOf: (id) => childrenById[id] ?? emptyChildren<Child>(),
    childVisible: (child) => !queryNormalized || childMatches(child, queryNormalized),
  };
}
