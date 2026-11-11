/**
 * Tests for the research strategy buy-and-hold benchmark chart model.
 *
 * USAGE:
 *   pnpm vitest run src/lib/components/strategies/research-strategy-chart-model.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  buildBuyHoldSeries,
  isRegisteredBenchmark,
  performanceValuePresentation,
  shouldAddBuyHoldOverlay,
} from './research-strategy-chart-model';

const INDEX = { ticker: 'IDX', label: 'Index' };

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('buildBuyHoldSeries', () => {
  it('aligns the benchmark to strategy dates and normalizes the first observation to $100', () => {
    const result = buildBuyHoldSeries(
      ['2024-01-02', '2024-01-03', '2024-01-05'],
      [
        { timestamp: '2024-01-01T00:00:00Z', close: 90 },
        { timestamp: '2024-01-02T00:00:00Z', close: 100 },
        { timestamp: '2024-01-03T00:00:00Z', close: 110 },
        { timestamp: '2024-01-04T00:00:00Z', close: 120 },
        { timestamp: '2024-01-05T00:00:00Z', close: 80 },
      ],
      INDEX,
    );

    expect(result).toMatchObject({
      metric: 'idx_buy_hold',
      label: 'Index buy & hold',
      isBenchmark: true,
      points_total: 3,
      points_returned: 3,
      points: [
        { x: '2024-01-02T00:00:00' },
        { x: '2024-01-03T00:00:00' },
        { x: '2024-01-05T00:00:00' },
      ],
    });
    expect(result?.points.map((point) => point.y)).toEqual([100, expect.closeTo(110), 80]);
  });

  it('recognizes registered benchmark identifiers without adding a duplicate series', () => {
    expect(isRegisteredBenchmark({ id: 'IDX' }, ['IDX'])).toBe(true);
    expect(isRegisteredBenchmark({ id: 'idx-usd-perpetual' }, ['IDX'])).toBe(true);
    expect(isRegisteredBenchmark({ id: 'named_control' }, ['IDX'])).toBe(false);
  });

  it('adds a distinct overlay only when the benchmark is not already a registered one', () => {
    expect(shouldAddBuyHoldOverlay('example-strategy', { id: 'named_control' }, ['IDX'])).toBe(
      true,
    );
    expect(shouldAddBuyHoldOverlay('example-strategy', { id: 'IDX' }, ['IDX'])).toBe(false);
    expect(shouldAddBuyHoldOverlay('example-strategy', { id: 'named_control' }, [])).toBe(false);
  });

  it('returns null instead of silently drawing an empty benchmark', () => {
    expect(
      buildBuyHoldSeries(
        ['2024-01-02'],
        [{ timestamp: '2024-01-01T00:00:00Z', close: 100 }],
        INDEX,
      ),
    ).toBeNull();
  });

  it('labels a non-USD performance surface as an index', () => {
    const presentation = performanceValuePresentation('index');

    expect(presentation.chartPrefix).not.toContain('$');
    expect(presentation.endingValueLabel).toBe('Ending index value');
    expect(presentation.endingValueFormat).toBe('number');
  });
});
