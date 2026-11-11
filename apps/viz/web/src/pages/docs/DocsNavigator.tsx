/**
 * Docs navigator: the package documentation tree on the shared Navigator.
 * Directories are disclosure rows (open by default), files link to
 * `/docs?doc=<path>`, generated files carry an `auto` tag, and a search keeps
 * only the matching files with their ancestor directories open.
 *
 * USAGE:
 *   <DocsNavigator tree={tree.root.children ?? []} selectedPath={selectedPath} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';

import type { DocsNode } from '@/lib/api/docs';
import { Navigator, type NavigatorNode } from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function toDocHref(path: string): string {
  return `/docs?doc=${encodeURIComponent(path)}`;
}

function matchesQuery(node: DocsNode, query: string): boolean {
  return node.title.toLowerCase().includes(query) || node.path.toLowerCase().includes(query);
}

/** Matching files plus the directories that contain them; the whole tree without a query. */
function filterTree(nodes: DocsNode[], query: string): DocsNode[] {
  if (!query) return nodes;
  const kept: DocsNode[] = [];
  for (const node of nodes) {
    if (node.type === 'file') {
      if (matchesQuery(node, query)) kept.push(node);
      continue;
    }
    const children = filterTree(node.children ?? [], query);
    if (children.length > 0) kept.push({ ...node, children });
  }
  return kept;
}

interface TreeContext {
  selectedPath: string;
  collapsed: Set<string>;
  searching: boolean;
  toggle: (path: string) => void;
}

function toNavigatorNode(node: DocsNode, context: TreeContext): NavigatorNode {
  if (node.type === 'file') {
    return {
      id: node.path,
      label: node.title,
      to: toDocHref(node.path),
      title: node.path,
      current: node.path === context.selectedPath,
      tag: node.generated ? { label: 'auto' } : undefined,
    };
  }
  return {
    id: node.path,
    label: node.title,
    title: node.path,
    expanded: context.searching || !context.collapsed.has(node.path),
    onToggle: () => context.toggle(node.path),
    children: (node.children ?? []).map((child) => toNavigatorNode(child, context)),
    empty: 'No documents in this directory.',
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface DocsNavigatorProps {
  tree: DocsNode[];
  selectedPath: string;
}

export function DocsNavigator({ tree, selectedPath }: DocsNavigatorProps) {
  const [query, setQuery] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  const queryNormalized = query.trim().toLowerCase();

  const toggle = (path: string) => {
    setCollapsed((paths) => {
      const next = new Set(paths);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const context: TreeContext = {
    selectedPath,
    collapsed,
    searching: queryNormalized !== '',
    toggle,
  };
  const items = filterTree(tree, queryNormalized).map((node) => toNavigatorNode(node, context));

  return (
    <Navigator
      title="Docs"
      titleTo="/docs"
      listLabel="Docs hierarchy"
      search={{
        id: 'docs-search',
        label: 'Search docs',
        placeholder: 'Search docs',
        value: query,
        onChange: setQuery,
      }}
      empty={query ? `No documents match “${query}”.` : 'No documents yet.'}
      items={items}
    />
  );
}
