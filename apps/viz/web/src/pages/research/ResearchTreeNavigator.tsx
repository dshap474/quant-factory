/**
 * Searchable tree navigator over a packages/research nav tree (the Research docs tree, the
 * Sandbox / Source tree), with an Overview row that leads to the section home.
 *
 * USAGE:
 *   <ResearchTreeNavigator title="Sandbox" home="/sandbox" nav={nav} loading={…} error={…} />
 *   <ResearchTreeNavigator title="Corpus" home="/corpus/sources" sections={[…]} … />
 *
 * Leaves are wired packages (their own route) or markdown docs; folders stay collapsed
 * unless they hold the active route or are listed in `open`, and every folder opens while
 * a search is active. With `sections`, each tree sits under its own label. A host `search`
 * puts the box above the tree and keeps the rows whose id it `matches` (a full-text search)
 * as well as those whose title matches.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';
import { useLocation } from 'react-router';
import type { ResearchNavNode } from '@/lib/api/research';
import { Input, Navigator, type NavigatorGroup, type NavigatorNode } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const NO_MATCHES: ReadonlySet<string> = new Set();

/** Leaves link somewhere; folders only hold children. */
function isLeaf(node: ResearchNavNode): boolean {
  return node.kind === 'package' || node.kind === 'doc';
}

function nodeMatchesQuery(
  node: ResearchNavNode,
  query: string,
  matches: ReadonlySet<string>,
): boolean {
  if (!query) return true;
  if (matches.has(node.id)) return true;
  if (node.title.toLowerCase().includes(query) || node.id.toLowerCase().includes(query)) {
    return true;
  }
  if (node.subtitle?.toLowerCase().includes(query)) return true;
  return (node.children ?? []).some((child) => nodeMatchesQuery(child, query, matches));
}

function filterNav(
  nodes: ResearchNavNode[],
  query: string,
  matches: ReadonlySet<string>,
): ResearchNavNode[] {
  if (!query) return nodes;
  return nodes
    .map((node) => {
      if (isLeaf(node)) return nodeMatchesQuery(node, query, matches) ? node : null;
      const children = filterNav(node.children ?? [], query, matches);
      if (children.length === 0 && !nodeMatchesQuery(node, query, matches)) return null;
      return { ...node, children };
    })
    .filter((node): node is ResearchNavNode => node !== null);
}

/** A leaf is current on its own route and on routes below it (a corpus work's chapters). */
function isCurrent(node: ResearchNavNode, pathname: string): boolean {
  return Boolean(node.route) && (pathname === node.route || pathname.startsWith(`${node.route}/`));
}

function collectActiveFolderIds(
  nodes: ResearchNavNode[],
  pathname: string,
  trail: string[] = [],
): string[] {
  for (const node of nodes) {
    const nextTrail = [...trail, node.id];
    if (isLeaf(node) && isCurrent(node, pathname)) return trail;
    if (node.children?.length) {
      const hit = collectActiveFolderIds(node.children, pathname, nextTrail);
      if (hit.length) return hit;
    }
  }
  return [];
}

interface TreeContext {
  home: string;
  /** Query string every link carries (a search's `?q=`), or ''. */
  linkSearch: string;
  pathname: string;
  expanded: Record<string, boolean>;
  searching: boolean;
  toggle: (id: string) => void;
}

function toNavigatorNode(node: ResearchNavNode, context: TreeContext): NavigatorNode {
  if (isLeaf(node)) {
    return {
      id: node.id,
      label: node.title,
      to: `${node.route ?? context.home}${context.linkSearch}`,
      title: node.subtitle ?? node.doc_path ?? node.title,
      current: isCurrent(node, context.pathname),
    };
  }
  // A folder with its own route (a book over its chapters) opens it as well as its children.
  return {
    id: node.id,
    label: node.title,
    to: node.route ? `${node.route}${context.linkSearch}` : undefined,
    title: node.subtitle ?? undefined,
    current: node.route ? context.pathname === node.route : undefined,
    expanded: context.searching || Boolean(context.expanded[node.id]),
    onToggle: () => context.toggle(node.id),
    children: (node.children ?? []).map((child) => toNavigatorNode(child, context)),
  };
}

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

/** One labelled tree in a navigator with several; a `homeLabel` leads it with a row to `home`. */
export interface ResearchTreeSection {
  id: string;
  label: string;
  home: string;
  homeLabel?: string;
  nav: ResearchNavNode[];
}

/** A search the host owns, shown as a box above the tree. */
export interface ResearchTreeSearch {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  /** Ids of rows a full-text search matched; kept alongside title matches. */
  matches?: ReadonlySet<string>;
  /** Query string every row's link carries, e.g. '?q=kelly'. */
  linkSearch?: string;
}

export interface ResearchTreeNavigatorProps {
  title: string;
  /** Section home: the title and the Overview row lead here. */
  home: string;
  /** Label of the row that leads to `home`. */
  homeLabel?: string;
  /** One unlabelled tree; ignored when `sections` is set. */
  nav?: ResearchNavNode[];
  /** Several trees, each under its label (in place of `nav`, `homeLabel`). */
  sections?: ResearchTreeSection[];
  loading: boolean;
  error: string | null;
  /** Folder ids open on first sight. */
  open?: string[];
  /** Noun for the empty and no-match messages, e.g. 'documents'. */
  noun: string;
  /** Host-owned search above the tree, in place of the bottom-bar title filter. */
  search?: ResearchTreeSearch;
}

export function ResearchTreeNavigator({
  title,
  home,
  homeLabel = 'Overview',
  nav = [],
  sections,
  loading,
  error,
  open = [],
  noun,
  search,
}: ResearchTreeNavigatorProps) {
  const { pathname } = useLocation();
  const [ownQuery, setOwnQuery] = useState('');
  const query = search?.value ?? ownQuery;
  const matches = search?.matches ?? NO_MATCHES;
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(open.map((id) => [id, true])),
  );

  const queryNormalized = query.trim().toLowerCase();
  const searching = queryNormalized.length > 0;

  // Open the active route's ancestors once per navigation, then leave the
  // folders under operator control (they stay collapsible).
  const [syncedPathname, setSyncedPathname] = useState<string | null>(null);
  const trees: ResearchTreeSection[] = sections ?? [
    { id: 'items', label: '', home, homeLabel, nav },
  ];
  const allNav = trees.flatMap((tree) => tree.nav);
  // Wait for every tree, or a later one would never open to the active route.
  if (syncedPathname !== pathname && !loading && allNav.length) {
    setSyncedPathname(pathname);
    const activeFolders = collectActiveFolderIds(allNav, pathname);
    if (activeFolders.length) {
      setExpanded((previous) => {
        const next = { ...previous };
        for (const id of activeFolders) next[id] = true;
        return next;
      });
    }
  }

  const toggle = (id: string) => setExpanded((previous) => ({ ...previous, [id]: !previous[id] }));
  const groups: NavigatorGroup[] = trees
    .map((tree) => {
      const context: TreeContext = {
        home: tree.home,
        linkSearch: search?.linkSearch ?? '',
        pathname,
        expanded,
        searching,
        toggle,
      };
      const homeRow: NavigatorNode[] =
        tree.homeLabel && (!searching || tree.homeLabel.toLowerCase().includes(queryNormalized))
          ? [
              {
                id: `${tree.id}:home`,
                label: tree.homeLabel,
                to: tree.home,
                current: pathname === tree.home,
              },
            ]
          : [];
      return {
        id: tree.id,
        label: tree.label || undefined,
        collapsible: Boolean(tree.label),
        items: [
          ...homeRow,
          ...filterNav(tree.nav, queryNormalized, matches).map((node) =>
            toNavigatorNode(node, context),
          ),
        ],
      };
    })
    .filter((group) => group.items.length > 0);
  const searchId = `${title.toLowerCase()}-search`;

  return (
    <Navigator
      title={title}
      titleTo={home}
      listLabel={`${title} tree`}
      search={
        search
          ? undefined
          : {
              id: searchId,
              label: `Search ${title.toLowerCase()}`,
              placeholder: `Search ${title.toLowerCase()}`,
              value: query,
              onChange: setOwnQuery,
            }
      }
      controls={
        search ? (
          <Input
            id={searchId}
            type="search"
            aria-label={search.placeholder}
            placeholder={search.placeholder}
            value={search.value}
            onChange={(event) => search.onChange(event.target.value)}
            autoComplete="off"
          />
        ) : undefined
      }
      loading={loading}
      error={error}
      empty={searching ? `No ${noun} match “${query.trim()}”.` : `No ${noun} yet.`}
      groups={groups}
    />
  );
}
