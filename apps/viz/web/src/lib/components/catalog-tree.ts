/**
 * Lake-mirroring tree model for the Data catalog navigator.
 *
 * Every catalog item is placed at `<resolution>/<category_path>` for each distinct
 * resolution it exposes, which reproduces the physical lake layout
 * `db/data/<layer>/<resolution>/<provider>/<group>/...`.
 *
 * USAGE:
 *   const nodes = buildCatalogTree(catalog.items);
 *   const visible = filterCatalogTree(nodes, 'funding');
 *   const open = collectDirPaths(visible);
 *   const reveal = collectItemAncestorPaths(visible, selectedItemId);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { LogicalCatalogItem } from '@/lib/api/catalog';
import { compareNatural } from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface CatalogTreeDir {
  kind: 'dir';
  key: string;
  name: string;
  path: string;
  children: CatalogTreeNode[];
}

export interface CatalogTreeLeaf {
  kind: 'leaf';
  key: string;
  name: string;
  path: string;
  item: LogicalCatalogItem;
  resolution: string | null;
}

export type CatalogTreeNode = CatalogTreeDir | CatalogTreeLeaf;

// --------------------------------------------------------------------------- #
// Build
// --------------------------------------------------------------------------- #

/** Distinct resolutions an item lives under, or `[null]` when it exposes none. */
function itemResolutions(item: LogicalCatalogItem): (string | null)[] {
  const seen: string[] = [];
  for (const option of item.resolutions) {
    if (!seen.includes(option.resolution)) seen.push(option.resolution);
  }
  if (seen.length) return seen;
  return item.default_resolution ? [item.default_resolution] : [null];
}

/**
 * Lake segments for one placement. The resolution segment is dropped when it
 * repeats the layer directory (registry keys such as `derived/reference/...`
 * physically live at `db/data/derived/reference/...`, not `derived/derived/...`).
 */
function placementSegments(item: LogicalCatalogItem, resolution: string | null): string[] {
  const category = item.category_path.split('/').filter(Boolean);
  if (!resolution || resolution === item.layer) return category;
  return [resolution, ...category];
}

function compareNodes(left: CatalogTreeNode, right: CatalogTreeNode): number {
  if (left.kind !== right.kind) return left.kind === 'dir' ? -1 : 1;
  return compareNatural(left.name, right.name);
}

function sortTree(nodes: CatalogTreeNode[]): CatalogTreeNode[] {
  nodes.sort(compareNodes);
  for (const node of nodes) {
    if (node.kind === 'dir') sortTree(node.children);
  }
  return nodes;
}

/** Build the directory tree for a flat catalog page, mirroring the lake layout. */
export function buildCatalogTree(items: LogicalCatalogItem[]): CatalogTreeNode[] {
  const roots: CatalogTreeNode[] = [];
  const directories = new Map<string, CatalogTreeDir>();

  for (const item of items) {
    for (const resolution of itemResolutions(item)) {
      const segments = placementSegments(item, resolution);
      if (!segments.length) continue;
      const leafName = segments[segments.length - 1];
      const categoryLabels = item.category_labels ?? item.category_path.split('/').filter(Boolean);
      const displayNames =
        resolution && resolution !== item.layer ? [resolution, ...categoryLabels] : categoryLabels;
      let siblings = roots;
      let parentPath = '';
      for (const [index, segment] of segments.slice(0, -1).entries()) {
        const path = parentPath ? `${parentPath}/${segment}` : segment;
        let directory = directories.get(path);
        if (!directory) {
          directory = {
            kind: 'dir',
            key: path,
            name: displayNames[index] ?? segment,
            path,
            children: [],
          };
          directories.set(path, directory);
          siblings.push(directory);
        }
        siblings = directory.children;
        parentPath = path;
      }
      const leafPath = parentPath ? `${parentPath}/${leafName}` : leafName;
      siblings.push({
        kind: 'leaf',
        key: `${leafPath}::${item.id}`,
        name: displayNames[displayNames.length - 1] ?? leafName,
        path: leafPath,
        item,
        resolution,
      });
    }
  }

  return sortTree(roots);
}

// --------------------------------------------------------------------------- #
// Search
// --------------------------------------------------------------------------- #

function leafHaystack(leaf: CatalogTreeLeaf): string {
  return `${leaf.path} ${leaf.item.category_labels?.join(' ') ?? ''} ${leaf.item.label} ${leaf.item.description ?? ''}`.toLowerCase();
}

/** Keep only leaves matching the query, along with their ancestor directories. */
export function filterCatalogTree(nodes: CatalogTreeNode[], query: string): CatalogTreeNode[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return nodes;
  const kept: CatalogTreeNode[] = [];
  for (const node of nodes) {
    if (node.kind === 'leaf') {
      if (leafHaystack(node).includes(needle)) kept.push(node);
      continue;
    }
    const children = filterCatalogTree(node.children, query);
    if (children.length) kept.push({ ...node, children });
  }
  return kept;
}

/** Every directory path in the tree, used to auto-expand search results. */
export function collectDirPaths(nodes: CatalogTreeNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.kind !== 'dir') continue;
    paths.push(node.path);
    paths.push(...collectDirPaths(node.children));
  }
  return paths;
}

/** Directory paths leading to any leaf for `itemId`, used to reveal a selection. */
export function collectItemAncestorPaths(
  nodes: CatalogTreeNode[],
  itemId: string | null,
): string[] {
  if (!itemId) return [];
  const paths = new Set<string>();
  const walk = (list: CatalogTreeNode[], trail: string[]) => {
    for (const node of list) {
      if (node.kind === 'leaf') {
        if (node.item.id === itemId) for (const path of trail) paths.add(path);
        continue;
      }
      walk(node.children, [...trail, node.path]);
    }
  };
  walk(nodes, []);
  return [...paths];
}

const UNIT_MINUTES: Record<string, number> = { m: 1, h: 60, d: 1440, w: 10080 };

/** Minutes in a timeframe name (`1m`, `5m`, `1h`, `1d`); null for any other name (`reference`). */
export function timeframeMinutes(name: string): number | null {
  if (name === 'tick') return 0;
  const match = /^(\d+)([mhdw])$/.exec(name);
  return match ? Number(match[1]) * (UNIT_MINUTES[match[2] ?? ''] ?? 0) : null;
}

/** Resolutions small to large (`1m`, `5m`, `1h`, `1d`); other names follow, by name. */
export function compareResolutions(left: string, right: string): number {
  const a = timeframeMinutes(left);
  const b = timeframeMinutes(right);
  if (a !== null && b !== null) return a - b;
  if (a !== null) return -1;
  if (b !== null) return 1;
  return compareNatural(left, right);
}

/**
 * Root directory to show for the timeframe selector.
 *
 * Priority: the operator's explicit choice, then the resolution of the selected
 * option, then any ancestor of the selection, then `1d`, then the first root. Raw
 * summary items appear under every resolution, so the ancestor fallback alone
 * would always land on the first root and silently drag the operator there.
 */
export function pickActiveRoot(
  dirs: CatalogTreeDir[],
  choice: string | null,
  selectedResolution: string | null,
  selectedRootPath: string | null,
): CatalogTreeDir | null {
  return (
    dirs.find((node) => node.name === choice) ??
    dirs.find((node) => node.name === selectedResolution) ??
    dirs.find((node) => node.path === selectedRootPath) ??
    dirs.find((node) => node.name === '1d') ??
    dirs[0] ??
    null
  );
}
