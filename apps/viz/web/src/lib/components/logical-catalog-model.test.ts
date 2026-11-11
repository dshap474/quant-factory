/**
 * Unit tests for the shared catalog detail URL parameter builder.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/components/logical-catalog-model.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import type { LogicalCatalogItem } from '@/lib/api/catalog';

import { buildCatalogDetailParams, familyMemberLabels, optionKey } from './logical-catalog-model';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function item(overrides: Partial<LogicalCatalogItem>): LogicalCatalogItem {
  return {
    id: 'dataset:vendorb/contracts/exchangex',
    kind: 'dataset',
    layer: 'raw',
    label: 'Contracts / Exchange X',
    category_path: 'vendorb/contracts/exchangex',
    description: null,
    domain: 'vendorb',
    status: 'active',
    asset_column: false,
    default_resolution: null,
    resolutions: [],
    ...overrides,
  };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('buildCatalogDetailParams', () => {
  it('addresses a raw family by category path and carries the clicked resolution', () => {
    const option = {
      resolution: '1d',
      scope: 'data' as const,
      path: 'raw/1d/vendorb/contracts/exchangex/aaa_contracts_exchangex.parquet',
      version: 'latest',
      updated_at: null,
      exists: true,
    };
    const base = new URLSearchParams({ layer: 'derived', item: 'dataset:other', option: 'stale' });

    const params = buildCatalogDetailParams(base, item({ resolutions: [option] }), 'raw', '1d');

    expect(Object.fromEntries(params)).toEqual({
      layer: 'raw',
      family: 'vendorb/contracts/exchangex',
      domain: 'vendorb',
      option: optionKey(option),
    });
  });

  it('addresses a derived item by id and preselects the clicked resolution', () => {
    const option = {
      resolution: '1d',
      scope: 'data' as const,
      path: 'derived/1d/crypto/example/surface/data.parquet',
      version: 'latest',
      updated_at: null,
      exists: true,
    };
    const base = new URLSearchParams({ family: 'vendorb/contracts/exchangex', domain: 'vendorb' });
    const derived = item({
      id: 'dataset:crypto/example/surface',
      layer: 'derived',
      category_path: 'crypto/example/surface',
      domain: 'crypto',
      resolutions: [option],
    });

    const params = buildCatalogDetailParams(base, derived, 'derived', '1d');

    expect(Object.fromEntries(params)).toEqual({
      layer: 'derived',
      item: 'dataset:crypto/example/surface',
      option: optionKey(option),
    });
  });

  it('drops the option when the clicked resolution has none', () => {
    const derived = item({ layer: 'derived', resolutions: [] });

    const params = buildCatalogDetailParams(new URLSearchParams(), derived, 'derived', '1h');

    expect(params.get('option')).toBeNull();
  });
});

describe('familyMemberLabels', () => {
  it('reduces per-asset files to the asset stem', () => {
    expect(
      familyMemberLabels([
        'raw/1d/vendorb/cash/exchangex/aaa_cash_exchangex.parquet',
        'raw/1d/vendorb/cash/exchangex/btc_cash_exchangex.parquet',
        'raw/1d/vendorb/cash/exchangex/1000xyz_cash_exchangex.parquet',
      ]),
    ).toEqual(['aaa', 'btc', '1000xyz']);
  });

  it('keeps partition directories that tell members apart', () => {
    expect(
      familyMemberLabels([
        'raw/1m/vendor/book/2024/01/btc_levels.parquet',
        'raw/1m/vendor/book/2024/02/btc_levels.parquet',
      ]),
    ).toEqual(['01', '02']);
  });

  it('falls back to full names when shortening collides or empties', () => {
    expect(familyMemberLabels([])).toEqual([]);
    expect(familyMemberLabels(['raw/1d/a/x.parquet'])).toEqual(['x']);
    expect(familyMemberLabels(['raw/a/b_x.parquet', 'raw/a/x.parquet'])).toEqual(['b_x', 'x']);
  });
});
