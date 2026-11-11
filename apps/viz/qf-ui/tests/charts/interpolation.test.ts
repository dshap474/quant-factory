/**
 * Interpolation vocabulary, precedence and ECharts mapping.
 *
 * USAGE:
 *   pnpm exec vitest run tests/charts/interpolation.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { echartsInterpolation, resolveInterpolation } from '../../src/charts/charts/interpolation';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('echartsInterpolation', () => {
  it('maps each interpolation to its ECharts series keys', () => {
    expect(echartsInterpolation('linear')).toEqual({ smooth: false, step: false });
    expect(echartsInterpolation('step-end')).toEqual({ smooth: false, step: 'end' });
    expect(echartsInterpolation('step-start')).toEqual({ smooth: false, step: 'start' });
    expect(echartsInterpolation('smooth')).toEqual({
      smooth: true,
      smoothMonotone: 'x',
      step: false,
    });
  });
});

describe('resolveInterpolation', () => {
  it('is linear when nothing is declared', () => {
    expect(resolveInterpolation()).toBe('linear');
  });

  it('prefers the series, then the component, then the legacy curve', () => {
    expect(resolveInterpolation('step-start', 'smooth', 'stepAfter')).toBe('step-start');
    expect(resolveInterpolation(undefined, 'smooth', 'stepAfter')).toBe('smooth');
    expect(resolveInterpolation(undefined, undefined, 'monotone')).toBe('smooth');
  });

  it("keeps the legacy curve 'stepAfter' drawing a step at the end", () => {
    expect(echartsInterpolation(resolveInterpolation(undefined, undefined, 'stepAfter'))).toEqual({
      smooth: false,
      step: 'end',
    });
  });
});
