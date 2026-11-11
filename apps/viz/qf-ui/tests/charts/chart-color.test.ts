/**
 * Named chart colours: palette slots and semantic tones resolve to the qf chart
 * bridge variables, and an opacity fades them with color-mix.
 *
 * USAGE:
 *   pnpm test -- chart-color.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';
import { chartColor, chartPaletteColor, withOpacity } from '../../src/charts/theme/chartColor';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('chartColor', () => {
  it('names palette slots and semantic tones', () => {
    expect(chartColor(1)).toBe('var(--qf-chart-1)');
    expect(chartColor(20)).toBe('var(--qf-chart-20)');
    expect(chartColor('positive')).toBe('var(--qf-chart-positive)');
    expect(chartColor('info')).toBe('var(--qf-chart-tone-info)');
    expect(chartColor('benchmark')).toBe('var(--qf-chart-benchmark)');
    expect(chartColor('foreground')).toBe('var(--qf-chart-strong-text)');
    expect(chartColor('neutral')).toBe('var(--qf-chart-neutral)');
  });

  it('fades by opacity and leaves full opacity untouched', () => {
    expect(chartColor(8, 0.55)).toBe('color-mix(in oklch, var(--qf-chart-8) 55%, transparent)');
    expect(chartColor('label', 1)).toBe('var(--qf-chart-label)');
    expect(withOpacity('rgb(1, 2, 3)', 0.05)).toBe(
      'color-mix(in oklch, rgb(1, 2, 3) 5%, transparent)',
    );
  });

  it('cycles a 0-based series index through the palette slots', () => {
    expect(chartPaletteColor(0)).toBe('var(--qf-chart-1)');
    expect(chartPaletteColor(19)).toBe('var(--qf-chart-20)');
    expect(chartPaletteColor(20)).toBe('var(--qf-chart-1)');
    expect(chartPaletteColor(-1)).toBe('var(--qf-chart-20)');
    expect(chartPaletteColor(2, 0.5)).toBe(
      'color-mix(in oklch, var(--qf-chart-3) 50%, transparent)',
    );
  });
});
