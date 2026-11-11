/**
 * Unit coverage for the terminal data-grid formatting helpers.
 *
 * USAGE: pnpm exec vitest run src/tables/core/format.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';
import { columnDecimalScale, columnFormat, compactDtype } from './format';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('columnDecimalScale', () => {
  it('takes the widest decimal scale on the page', () => {
    expect(columnDecimalScale([38470, 38470.16])).toBe(2);
    expect(columnDecimalScale([1, 2, 3])).toBe(0);
    expect(columnDecimalScale([])).toBe(0);
  });

  it('ignores non-numeric values and caps runaway precision', () => {
    expect(columnDecimalScale(['x', null, 1.5])).toBe(1);
    expect(columnDecimalScale([1 / 3])).toBe(8);
  });
});

describe('columnFormat', () => {
  it('marks all-number columns numeric with a shared scale', () => {
    expect(columnFormat([38470, 38470.16, null], false)).toEqual({ numeric: true, scale: 2 });
  });

  it('refuses mixed, empty, and temporal columns', () => {
    expect(columnFormat([1, 'a'], false)).toEqual({ numeric: false, scale: 0 });
    expect(columnFormat([null, null], false)).toEqual({ numeric: false, scale: 0 });
    expect(columnFormat([1, 2], true)).toEqual({ numeric: false, scale: 0 });
  });
});

describe('compactDtype', () => {
  it('abbreviates polars scalar and temporal dtypes', () => {
    expect(compactDtype('Float64')).toBe('f64');
    expect(compactDtype('String')).toBe('str');
    expect(compactDtype("Datetime(time_unit='us', time_zone=None)")).toBe('datetime[\u03bcs]');
    expect(compactDtype("Datetime(time_unit='ms', time_zone='UTC')")).toBe('datetime[ms, UTC]');
  });

  it('falls back to a lowercased label', () => {
    expect(compactDtype('Struct')).toBe('struct');
  });
});
