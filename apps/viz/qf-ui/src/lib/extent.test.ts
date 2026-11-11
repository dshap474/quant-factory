/**
 * Unit tests for the loop-based extent helpers.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/extent.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { extentBy, extentOf } from './extent';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('extentOf', () => {
  it('returns undefined for an empty array', () => {
    expect(extentOf([])).toBeUndefined();
  });

  it('returns the value itself for a single element', () => {
    expect(extentOf([3.5])).toEqual({ min: 3.5, max: 3.5 });
  });

  it('computes min and max over mixed values', () => {
    expect(extentOf([2, -7, 0, 11, 4])).toEqual({ min: -7, max: 11 });
  });

  it('skips NaN, null, and undefined values', () => {
    expect(extentOf([NaN, 5, null, -2, undefined, NaN])).toEqual({ min: -2, max: 5 });
  });

  it('returns undefined when every value is unusable', () => {
    expect(extentOf([NaN, null, undefined])).toBeUndefined();
  });

  it('handles a 1e6-element array without a RangeError', () => {
    const values = new Array<number>(1_000_000);
    for (let index = 0; index < values.length; index += 1) values[index] = index - 500_000;
    // The spread form `Math.max(...values)` throws RangeError at this size.
    expect(extentOf(values)).toEqual({ min: -500_000, max: 499_999 });
  });
});

describe('extentBy', () => {
  it('applies the accessor and skips unusable accessor results', () => {
    const points = [{ value: 4 }, { value: NaN }, { value: -1 }, { value: null }];
    expect(extentBy(points, (point) => point.value)).toEqual({ min: -1, max: 4 });
  });

  it('returns undefined for an empty array', () => {
    expect(extentBy([], (item: { value: number }) => item.value)).toBeUndefined();
  });
});
