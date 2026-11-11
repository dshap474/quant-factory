/**
 * Tests for canonical dataset chart benchmark overlay conversion.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/components/charts/dataset-chart-overlays.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  parsePriceOverlayPoints,
  priceOverlayOptions,
  resolvePriceOverlay,
} from './dataset-chart-overlays';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

const REGISTERED = [
  { ticker: 'IDX', label: 'Index', description: 'Example index' },
  { ticker: 'ALT', label: 'Alternative', description: 'Example alternative' },
];

describe('dataset chart overlays', () => {
  it('only exposes overlays backed by registered benchmark endpoints', () => {
    expect(priceOverlayOptions(REGISTERED)).toEqual([
      { value: 'none', label: 'None', ticker: null },
      { value: 'IDX', label: 'Index', ticker: 'IDX' },
      { value: 'ALT', label: 'Alternative', ticker: 'ALT' },
    ]);
    expect(priceOverlayOptions([])).toEqual([{ value: 'none', label: 'None', ticker: null }]);
  });

  it('opens every chart with the first registered benchmark overlay', () => {
    expect(resolvePriceOverlay(priceOverlayOptions(REGISTERED), null).ticker).toBe('IDX');
    expect(resolvePriceOverlay(priceOverlayOptions([]), null).value).toBe('none');
    expect(resolvePriceOverlay(priceOverlayOptions(REGISTERED), 'none').value).toBe('none');
  });

  it('converts benchmark rows into plot points', () => {
    expect(
      parsePriceOverlayPoints([
        { timestamp: '2026-07-29T00:00:00Z', close: 117_000 },
        { timestamp: 'invalid', close: 1 },
      ]),
    ).toEqual([{ date: new Date('2026-07-29T00:00:00Z'), value: 117_000 }]);
  });
});
