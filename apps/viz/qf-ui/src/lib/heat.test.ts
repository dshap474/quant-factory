/**
 * Tests for the shared heat scale (divergingCellColor).
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/heat.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { divergingCellColor, rankCellColor } from './heat';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('divergingCellColor', () => {
  it('diverges on sign and scales opacity 14%-88% by |value| / maxAbs', () => {
    expect(divergingCellColor(0)).toBe(
      'color-mix(in oklch, var(--qf-chart-positive) 14%, transparent)',
    );
    expect(divergingCellColor(-1)).toBe(
      'color-mix(in oklch, var(--qf-chart-negative) 88%, transparent)',
    );
    expect(divergingCellColor(0.04, { maxAbs: 0.08 })).toBe(
      'color-mix(in oklch, var(--qf-chart-positive) 51%, transparent)',
    );
    expect(divergingCellColor(5, { maxAbs: 0.08 })).toBe(
      'color-mix(in oklch, var(--qf-chart-positive) 88%, transparent)',
    );
  });

  it('scales magnitude on the info tone', () => {
    expect(divergingCellColor(-0.5, { magnitude: true })).toBe(
      'color-mix(in oklch, var(--qf-chart-tone-info) 51%, transparent)',
    );
  });

  it('leaves missing values transparent', () => {
    expect(divergingCellColor(null)).toBe('transparent');
    expect(divergingCellColor(undefined)).toBe('transparent');
    expect(divergingCellColor(Number.NaN)).toBe('transparent');
  });
});

describe('rankCellColor', () => {
  it('runs success through warning to critical by relative position', () => {
    expect(rankCellColor(0)).toBe(
      'color-mix(in oklab, color-mix(in oklab, var(--color-tone-warning) 0%, var(--color-tone-success)) 22%, transparent)',
    );
    expect(rankCellColor(0.5)).toContain(
      'var(--color-tone-warning) 100%, var(--color-tone-success)',
    );
    expect(rankCellColor(0.75)).toContain(
      'var(--color-tone-critical) 50%, var(--color-tone-warning)',
    );
    expect(rankCellColor(1)).toContain('var(--color-tone-critical) 100%');
  });
  it('keeps singleton, all-equal and missing standings neutral', () => {
    expect(rankCellColor(null)).toBe('transparent');
    expect(rankCellColor(undefined)).toBe('transparent');
    expect(rankCellColor(Number.NaN)).toBe('transparent');
  });
});
