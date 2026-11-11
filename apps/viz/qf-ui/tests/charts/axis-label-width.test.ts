/**
 * Value-axis label width estimation used to size a linked stack's shared gutter.
 *
 * USAGE:
 *   pnpm test -- tests/charts/axis-label-width.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  axisLabelSamples,
  axisLabelWidth,
  extremeLabelVisibility,
  measureLabelWidth,
} from '../../src/charts/charts/axisLabelWidth';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('axisLabelSamples', () => {
  it('samples the domain ends and the nice interior ticks of a value axis', () => {
    expect(axisLabelSamples([0, 1], 'linear', 4)).toEqual([0, 1, 0.3, 0.6, 0.9]);
    expect(axisLabelSamples([-1.3, 2.7], 'linear', 3)).toEqual([-1.3, 2.7, -1, 0, 1, 2]);
  });

  it('samples the powers of ten inside a log axis', () => {
    expect(axisLabelSamples([50, 25_000], 'log', 3)).toEqual([50, 25_000, 100, 1_000, 10_000]);
    expect(axisLabelSamples([0, 10], 'log', 3)).toEqual([0, 10]);
  });

  it('returns nothing for an empty or unbounded domain', () => {
    expect(axisLabelSamples(null, 'linear', 3)).toEqual([]);
    expect(axisLabelSamples([0, Number.POSITIVE_INFINITY], 'linear', 3)).toEqual([]);
  });
});

describe('measureLabelWidth', () => {
  it('estimates from the longest label when no canvas can measure text', () => {
    expect(measureLabelWidth([], 12)).toBe(0);
    expect(measureLabelWidth(['1', '$120.5k'], 12)).toBeCloseTo(7 * 12 * 0.6);
  });
});

describe('axisLabelWidth', () => {
  it('formats the sampled ticks the way the axis will before measuring', () => {
    const width = axisLabelWidth({
      domain: [80_000, 120_000],
      scale: 'log',
      splitNumber: 3,
      format: (value) => `$${(value / 1_000).toFixed(1)}k`,
      fontSize: 12,
    });
    // '$120.0k' and '$100.0k' are the widest at seven characters.
    expect(width).toBeCloseTo(7 * 12 * 0.6);
  });
});

describe('extremeLabelVisibility', () => {
  it('hides padded linear ends that are off the tick ladder', () => {
    expect(extremeLabelVisibility([5.03, 114.14], 'linear')).toEqual({
      showMinLabel: false,
      showMaxLabel: false,
    });
  });

  it('keeps ends that land on a nice tick', () => {
    expect(extremeLabelVisibility([0, 100], 'linear')).toEqual({});
    expect(extremeLabelVisibility([-20, 37.05], 'linear')).toEqual({ showMaxLabel: false });
  });

  it('treats powers of ten as the log tick ladder', () => {
    expect(extremeLabelVisibility([37.05, 28_300], 'log')).toEqual({
      showMinLabel: false,
      showMaxLabel: false,
    });
    expect(extremeLabelVisibility([10, 28_300], 'log')).toEqual({ showMaxLabel: false });
  });

  it('leaves the ends alone when too few nice ticks would remain', () => {
    expect(extremeLabelVisibility([20, 80], 'log')).toEqual({});
    expect(extremeLabelVisibility(undefined, 'linear')).toEqual({});
  });
});
