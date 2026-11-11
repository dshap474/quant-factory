/**
 * Unit tests for the shared table sort helpers.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/core/sort.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { ariaSort, compareValues, nextSort, sortRows } from './sort';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('nextSort', () => {
  it('starts a new column at the initial direction', () => {
    expect(nextSort(null, 'close')).toEqual({ column: 'close', direction: 'asc' });
    expect(nextSort({ column: 'asset', direction: 'asc' }, 'close', 'desc')).toEqual({
      column: 'close',
      direction: 'desc',
    });
  });

  it('flips the active column', () => {
    expect(nextSort({ column: 'close', direction: 'desc' }, 'close')).toEqual({
      column: 'close',
      direction: 'asc',
    });
    expect(nextSort({ column: 'close', direction: 'asc' }, 'close')).toEqual({
      column: 'close',
      direction: 'desc',
    });
  });
});

describe('ariaSort', () => {
  it('maps the active column direction and none otherwise', () => {
    expect(ariaSort(null, 'close')).toBe('none');
    expect(ariaSort({ column: 'close', direction: 'asc' }, 'close')).toBe('ascending');
    expect(ariaSort({ column: 'close', direction: 'desc' }, 'close')).toBe('descending');
    expect(ariaSort({ column: 'close', direction: 'desc' }, 'asset')).toBe('none');
  });
});

describe('compareValues', () => {
  it('orders numbers numerically and text with numeric collation', () => {
    expect(compareValues(2, 10)).toBeLessThan(0);
    expect(compareValues('item2', 'item10')).toBeLessThan(0);
    expect(compareValues('b', 'A')).toBeGreaterThan(0);
  });
});

describe('sortRows', () => {
  const rows = [
    { asset: 'ETH', close: 3 },
    { asset: 'BTC', close: null },
    { asset: 'SOL', close: 1 },
    { asset: 'ADA', close: 3 },
  ];

  it('returns a copy in source order without a sort', () => {
    const out = sortRows(rows, null);
    expect(out).toEqual(rows);
    expect(out).not.toBe(rows);
  });

  it('sorts descending with missing values last and stable ties', () => {
    expect(sortRows(rows, { column: 'close', direction: 'desc' }).map((r) => r.asset)).toEqual([
      'ETH',
      'ADA',
      'SOL',
      'BTC',
    ]);
  });

  it('sorts ascending with missing values still last', () => {
    expect(sortRows(rows, { column: 'close', direction: 'asc' }).map((r) => r.asset)).toEqual([
      'SOL',
      'ETH',
      'ADA',
      'BTC',
    ]);
    expect(sortRows(rows, { column: 'asset', direction: 'asc' }).map((r) => r.asset)).toEqual([
      'ADA',
      'BTC',
      'ETH',
      'SOL',
    ]);
  });
});
