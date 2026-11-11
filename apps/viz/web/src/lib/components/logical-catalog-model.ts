/**
 * Shared value types and display helpers for the logical catalog workspace.
 *
 * USAGE:
 *   const key = optionKey(option);
 *   const params = buildCatalogDetailParams(searchParams, item, 'raw', '1d');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { LogicalCatalogItem, LogicalCatalogOption } from '@/lib/api/catalog';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type DataLayer = 'raw' | 'corrected' | 'derived';

/** Corrected datasets mirror raw paths, so they are browsed as raw families. */
export function isRawLike(layer: string | null | undefined): layer is 'raw' | 'corrected' {
  return layer === 'raw' || layer === 'corrected';
}

export function readDataLayer(value: string | null): DataLayer {
  return value === 'derived' || value === 'corrected' ? value : 'raw';
}
export type WorkspaceParams = Record<string, string | null>;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

export function optionKey(option: LogicalCatalogOption): string {
  return `${option.version}::${option.resolution}::${option.path}`;
}

/**
 * URL params that address one catalog item on the detail workspace. Raw families
 * are addressed by `family` (summary ids are not stable selections), derived
 * items by `item` plus the option matching the clicked resolution.
 */
export function buildCatalogDetailParams(
  base: URLSearchParams,
  item: LogicalCatalogItem,
  layer: DataLayer,
  resolution?: string | null,
): URLSearchParams {
  const params = new URLSearchParams(base);
  params.set('layer', layer);
  if (isRawLike(layer)) {
    params.delete('item');
    params.set('family', item.category_path);
    if (item.domain) params.set('domain', item.domain);
    else params.delete('domain');
  } else {
    params.delete('family');
    params.delete('domain');
    params.set('item', item.id);
  }
  // The clicked resolution directory is the user's intent, so carry its option
  // instead of letting the workspace fall back to an arbitrary first entry.
  const option = item.resolutions.find((entry) => entry.resolution === resolution);
  if (option) params.set('option', optionKey(option));
  else params.delete('option');
  return params;
}

/**
 * Short, unique labels for the parquet files of one raw family: drop the
 * directory prefix and `.parquet`, then the suffix every file shares at a `_`
 * or `/` boundary, so `…/venue/btc_spot_venue.parquet` reads `btc`. Falls
 * back to the prefix-stripped names when shortening would collide.
 */
export function familyMemberLabels(paths: readonly string[]): string[] {
  if (paths.length === 0) return [];
  const parts = paths.map((path) => path.replace(/\.parquet$/, '').split('/'));
  let prefix = 0;
  while (
    parts.every((segments) => segments.length > prefix + 1) &&
    parts.every((segments) => segments[prefix] === parts[0]?.[prefix])
  ) {
    prefix += 1;
  }
  const names = parts.map((segments) => segments.slice(prefix).join('/'));
  if (names.length < 2) return names;

  let suffix = names[0] ?? '';
  for (const name of names) {
    while (suffix && !name.endsWith(suffix)) suffix = suffix.slice(1);
  }
  const boundary = suffix.search(/[_/]/);
  suffix = boundary === -1 ? '' : suffix.slice(boundary);
  const short = suffix ? names.map((name) => name.slice(0, -suffix.length)) : names;
  const usable = short.every(Boolean) && new Set(short).size === short.length;
  return usable ? short : names;
}
