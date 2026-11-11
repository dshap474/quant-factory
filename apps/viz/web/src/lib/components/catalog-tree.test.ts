/**
 * Unit tests for the lake-mirroring catalog tree model.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/components/catalog-tree.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import type { LogicalCatalogItem, LogicalCatalogOption } from '@/lib/api/catalog';

import {
  buildCatalogTree,
  type CatalogTreeDir,
  type CatalogTreeNode,
  collectDirPaths,
  collectItemAncestorPaths,
  filterCatalogTree,
  pickActiveRoot,
} from './catalog-tree';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function option(resolution: string, path: string): LogicalCatalogOption {
  return { resolution, scope: 'data', path, version: 'latest', updated_at: null, exists: true };
}

function item(
  overrides: Partial<LogicalCatalogItem> & Pick<LogicalCatalogItem, 'id' | 'category_path'>,
): LogicalCatalogItem {
  return {
    kind: 'dataset',
    layer: 'raw',
    label: overrides.category_path,
    description: null,
    domain: null,
    status: 'active',
    asset_column: false,
    default_resolution: null,
    resolutions: [],
    ...overrides,
  };
}

function paths(nodes: CatalogTreeNode[]): string[] {
  return nodes.flatMap((node) =>
    node.kind === 'dir' ? [`${node.path}/`, ...paths(node.children)] : [node.path],
  );
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('buildCatalogTree', () => {
  it('places a family under every distinct resolution directory', () => {
    const tree = buildCatalogTree([
      item({
        id: 'dataset:vendorb/contracts/assets',
        category_path: 'vendorb/contracts/assets',
        resolutions: [
          option('1d', 'raw/1d/vendorb/contracts/assets/data.parquet'),
          option('1h', 'raw/1h/vendorb/contracts/assets/data.parquet'),
          option('1h', 'raw/1h/vendorb/contracts/assets/extra.parquet'),
        ],
      }),
    ]);

    expect(paths(tree)).toEqual([
      '1d/',
      '1d/vendorb/',
      '1d/vendorb/contracts/',
      '1d/vendorb/contracts/assets',
      '1h/',
      '1h/vendorb/',
      '1h/vendorb/contracts/',
      '1h/vendorb/contracts/assets',
    ]);
  });

  it('sorts directories before leaves and drops a resolution repeating the layer', () => {
    const tree = buildCatalogTree([
      item({
        id: 'dataset:reference/asset-identity',
        layer: 'derived',
        category_path: 'reference/asset-identity',
        resolutions: [option('derived', 'derived/reference/asset-identity/data.parquet')],
      }),
      item({
        id: 'dataset:crypto/example/surface',
        layer: 'derived',
        category_path: 'crypto/example/surface',
        resolutions: [option('1d', 'derived/1d/crypto/example/surface/data.parquet')],
      }),
    ]);

    expect(paths(tree)).toEqual([
      '1d/',
      '1d/crypto/',
      '1d/crypto/example/',
      '1d/crypto/example/surface',
      'reference/',
      'reference/asset-identity',
    ]);
  });

  it('falls back to the default resolution when no options are present', () => {
    const tree = buildCatalogTree([
      item({ id: 'dataset:macro', category_path: 'macro', default_resolution: '1d' }),
    ]);

    expect(paths(tree)).toEqual(['1d/', '1d/macro']);
  });
});

describe('filterCatalogTree', () => {
  const tree = buildCatalogTree([
    item({
      id: 'dataset:vendorb/rates/assets',
      category_path: 'vendorb/rates/assets',
      resolutions: [option('1h', 'raw/1h/vendorb/rates/assets/data.parquet')],
    }),
    item({
      id: 'dataset:vendorb/cash/assets',
      category_path: 'vendorb/cash/assets',
      resolutions: [option('1h', 'raw/1h/vendorb/cash/assets/data.parquet')],
    }),
  ]);

  it('keeps matching leaves with their ancestors', () => {
    const filtered = filterCatalogTree(tree, 'RATES');

    expect(paths(filtered)).toEqual([
      '1h/',
      '1h/vendorb/',
      '1h/vendorb/rates/',
      '1h/vendorb/rates/assets',
    ]);
    expect(collectDirPaths(filtered)).toEqual(['1h', '1h/vendorb', '1h/vendorb/rates']);
  });

  it('returns the full tree for an empty query', () => {
    expect(filterCatalogTree(tree, '  ')).toBe(tree);
  });
});

describe('collectItemAncestorPaths', () => {
  const tree = buildCatalogTree([
    item({
      id: 'dataset:vendorb/contracts/assets',
      category_path: 'vendorb/contracts/assets',
      resolutions: [
        option('1d', 'raw/1d/vendorb/contracts/assets/data.parquet'),
        option('1h', 'raw/1h/vendorb/contracts/assets/data.parquet'),
      ],
    }),
    item({
      id: 'dataset:vendorb/cash/assets',
      category_path: 'vendorb/cash/assets',
      resolutions: [option('1d', 'raw/1d/vendorb/cash/assets/data.parquet')],
    }),
  ]);

  it('returns every directory leading to the selected item', () => {
    expect(collectItemAncestorPaths(tree, 'dataset:vendorb/contracts/assets')).toEqual([
      '1d',
      '1d/vendorb',
      '1d/vendorb/contracts',
      '1h',
      '1h/vendorb',
      '1h/vendorb/contracts',
    ]);
  });

  it('returns nothing without a selection', () => {
    expect(collectItemAncestorPaths(tree, null)).toEqual([]);
  });
});

describe('pickActiveRoot', () => {
  const tree = buildCatalogTree([
    item({
      id: 'dataset:vendorb/contracts/exchangex',
      category_path: 'vendorb/contracts/exchangex',
      resolutions: [
        option('1d', 'raw/1d/vendorb/contracts/exchangex/data.parquet'),
        option('5m', 'raw/5m/vendorb/contracts/exchangex/data.parquet'),
      ],
    }),
  ]);
  const dirs = tree.filter((node) => node.kind === 'dir') as CatalogTreeDir[];

  it('prefers the operator choice', () => {
    expect(pickActiveRoot(dirs, '5m', '1d', '1d')?.name).toBe('5m');
  });

  it('falls back to the selected option resolution, not the first ancestor', () => {
    expect(pickActiveRoot(dirs, null, '5m', '1d')?.name).toBe('5m');
  });

  it('falls back to the selection ancestor, then the first root', () => {
    expect(pickActiveRoot(dirs, null, null, '5m')?.name).toBe('5m');
    expect(pickActiveRoot(dirs, null, null, null)?.name).toBe('1d');
    expect(pickActiveRoot([], null, null, null)).toBeNull();
  });
});
