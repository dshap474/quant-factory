/**
 * Width-independent line thinning: dense series keep their exact extent and their gaps.
 *
 * USAGE:
 *   pnpm vitest run --project charts tests/charts/line-decimation.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  decimateLineData,
  LINE_DECIMATION_THRESHOLD,
  type QfLineDatum,
} from '../../src/charts/charts/lineDecimation';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function series(length: number, value: (index: number) => number | '-'): QfLineDatum[] {
  return Array.from({ length }, (_, index) => [index * 86_400_000, value(index)]);
}

function extent(data: readonly QfLineDatum[]): [number, number] {
  const values = data.flatMap(([, value]) => (value === '-' ? [] : [value]));
  return [Math.min(...values), Math.max(...values)];
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('decimateLineData', () => {
  it('leaves series at or below the threshold untouched', () => {
    const data = series(LINE_DECIMATION_THRESHOLD, (index) => index);
    expect(decimateLineData(data)).toBe(data);
  });

  it('keeps the exact extent, endpoints, and time order of a dense series', () => {
    const data = series(
      20_000,
      (index) => Math.sin(index / 37) * 100 + (index === 12_345 ? 900 : 0),
    );
    const thinned = decimateLineData(data);
    expect(thinned.length).toBeLessThan(data.length / 4);
    expect(extent(thinned)).toEqual(extent(data));
    expect(thinned[0]).toBe(data[0]);
    expect(thinned.at(-1)).toBe(data.at(-1));
    const times = thinned.map(([time]) => time);
    expect(times).toEqual([...times].sort((a, b) => a - b));
  });

  it('keeps an extreme that follows a gap, and keeps the gap', () => {
    const data = series(10_000, (index) => (index === 5_000 ? '-' : index === 5_001 ? -500 : 1));
    const thinned = decimateLineData(data);
    expect(extent(thinned)).toEqual([-500, 1]);
    expect(thinned.some(([, value]) => value === '-')).toBe(true);
  });
});
