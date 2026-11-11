/**
 * Tests for bounded wide-dataset column selection.
 *
 * USAGE:
 *   pnpm test -- dataset-columns.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  selectDatasetColumns,
  selectIdentityColumns,
  showsColumnControls,
} from './dataset-columns';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('dataset column selection', () => {
  it('pins at most two identity columns in priority order', () => {
    expect(selectIdentityColumns(['ticker', 'value', 'symbol', 'date', 'timestamp'])).toEqual([
      'timestamp',
      'date',
    ]);
  });

  it('pages fifty browsable columns while retaining identity columns', () => {
    const columns = [
      'timestamp',
      'symbol',
      ...Array.from({ length: 110 }, (_, index) => `f_${index}`),
    ];

    const result = selectDatasetColumns(columns, '', 2);

    expect(result.selected).toHaveLength(52);
    expect(result.selected.slice(0, 2)).toEqual(['timestamp', 'symbol']);
    expect(result.start).toBe(51);
    expect(result.end).toBe(100);
    expect(result.totalPages).toBe(3);
  });

  it('searches columns and clamps an out-of-range page', () => {
    const result = selectDatasetColumns(
      ['date', 'price_open', 'price_close', 'volume'],
      'price',
      9,
    );

    expect(result.page).toBe(1);
    expect(result.selected).toEqual(['date', 'price_open', 'price_close']);
    expect(result.totalBrowsable).toBe(2);
  });
});

it('keeps the column controls on a wide panel even under compact chrome', () => {
  const wide = selectDatasetColumns(
    ['timestamp', 'asset', ...Array.from({ length: 200 }, (_, i) => `feature_${i}`)],
    '',
    1,
  );
  // 200 browsable columns span 4 pages: hiding the pager would strand 150 of them.
  expect(wide.totalPages).toBe(4);
  expect(showsColumnControls(true, wide.totalPages, '')).toBe(true);
});

it('drops the column controls only when one page holds every column', () => {
  const narrow = selectDatasetColumns(['timestamp', 'asset', 'close', 'volume'], '', 1);
  expect(narrow.totalPages).toBe(1);
  expect(showsColumnControls(true, narrow.totalPages, '')).toBe(false);
  // A live search must stay editable, or the operator cannot clear it.
  expect(showsColumnControls(true, narrow.totalPages, 'clo')).toBe(true);
  expect(showsColumnControls(false, narrow.totalPages, '')).toBe(true);
});
