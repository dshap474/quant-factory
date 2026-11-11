/**
 * Segmented area boundary contracts.
 *
 * USAGE:
 *   pnpm test -- tests/charts/segmented-area-series.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  buildSegmentedAreaSeries,
  type SegmentedAreaPoint,
} from '../../src/charts/charts/segmentedAreaSeries';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

type Segment = 'a' | 'b';

const DAY_MS = 24 * 60 * 60 * 1000;
const START = new Date('2026-01-01T00:00:00Z').getTime();
const SEGMENTS = [
  { id: 'a', color: 'blue' },
  { id: 'b', color: 'red' },
] as const;

function point(day: number, value: number, segment: Segment): SegmentedAreaPoint<Segment> {
  return { date: new Date(START + day * DAY_MS), value, segment };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('buildSegmentedAreaSeries', () => {
  it('creates a hard gradient stop between adjacent segments', () => {
    const series = buildSegmentedAreaSeries({
      points: [point(0, 1, 'a'), point(1, 3, 'b')],
      segments: SEGMENTS,
    });

    expect(series).toHaveLength(1);
    expect(series[0]?.areaFill).toEqual({
      stops: [
        { offset: 0, color: 'blue' },
        { offset: 0.5, color: 'blue' },
        { offset: 0.5, color: 'red' },
        { offset: 1, color: 'red' },
      ],
    });
  });

  it("puts the step-end stop where the step happens, on the new segment's first point", () => {
    const series = buildSegmentedAreaSeries({
      points: [point(0, 1, 'a'), point(1, 2, 'a'), point(2, 3, 'b'), point(4, 3, 'b')],
      segments: SEGMENTS,
      interpolation: 'step-end',
    });

    expect(series[0]?.interpolation).toBe('step-end');
    expect(series[0]?.areaFill).toEqual({
      stops: [
        { offset: 0, color: 'blue' },
        { offset: 0.5, color: 'blue' },
        { offset: 0.5, color: 'red' },
        { offset: 1, color: 'red' },
      ],
    });
  });

  it('gives a one-point segment a visible interval between transition midpoints', () => {
    const series = buildSegmentedAreaSeries({
      points: [point(0, 1, 'a'), point(1, 2, 'b'), point(2, 3, 'a')],
      segments: SEGMENTS,
    });

    expect(series).toHaveLength(1);
    expect(series[0]?.areaFill).toEqual({
      stops: [
        { offset: 0, color: 'blue' },
        { offset: 0.25, color: 'blue' },
        { offset: 0.25, color: 'red' },
        { offset: 0.75, color: 'red' },
        { offset: 0.75, color: 'blue' },
        { offset: 1, color: 'blue' },
      ],
    });
  });

  it('keeps consecutive points from one segment in one series', () => {
    const series = buildSegmentedAreaSeries({
      points: [point(0, 1, 'a'), point(1, 2, 'a'), point(2, 3, 'a')],
      segments: SEGMENTS,
    });

    expect(series).toHaveLength(1);
    expect(series[0]?.data).toHaveLength(3);
    expect(series[0]?.areaFill).toEqual({
      stops: [
        { offset: 0, color: 'blue' },
        { offset: 1, color: 'blue' },
      ],
    });
  });
});
