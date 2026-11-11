/**
 * ECharts text options must carry a concrete font family, never a CSS custom property.
 *
 * USAGE:
 *   pnpm exec vitest run canvas-font-resolution.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { withBaseTextStyle } from '../../src/charts/core/QfChart';
import { qfEChartsTooltip } from '../../src/charts/core/tooltip';
import type { QfChartTheme } from '../../src/charts/hooks/useChartTheme';
import { QF_CHART_FONT_SANS_FALLBACK, resolveChartFont } from '../../src/charts/theme/tokens';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

const THEME = {
  axisFontSize: 12,
  tooltipBackground: '#101418',
  tooltipBorder: '#22282e',
  tooltipText: '#e8edf2',
};

const CHART_THEME = {
  axis: '#a0a4a8',
  axisFontSize: 12,
  fontFamily: resolveChartFont(),
} as QfChartTheme;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('canvas font resolution', () => {
  it('resolves the chart sans font to a concrete family list', () => {
    const font = resolveChartFont();
    expect(font).not.toContain('var(');
    expect(font.length).toBeGreaterThan(0);
    expect(font).toContain('sans-serif');
  });

  it('falls back to a literal family list when the host token is undefined', () => {
    expect(QF_CHART_FONT_SANS_FALLBACK).not.toContain('var(');
    expect(resolveChartFont()).toBe(QF_CHART_FONT_SANS_FALLBACK);
  });

  it('gives every option without a text style the token sans base style', () => {
    const option = withBaseTextStyle({ series: [] }, CHART_THEME);
    expect(option.textStyle).toEqual({
      fontFamily: resolveChartFont(),
      fontSize: 12,
      color: '#a0a4a8',
    });
    expect(option.series).toEqual([]);
  });

  it('leaves an option that sets its own text style untouched', () => {
    const option = { textStyle: { fontFamily: 'serif' } };
    expect(withBaseTextStyle(option, CHART_THEME)).toBe(option);
  });

  it('hands ECharts tooltips a resolved font family', () => {
    const fontFamily = qfEChartsTooltip(THEME).textStyle.fontFamily;
    expect(fontFamily).not.toContain('var(');
    expect(fontFamily).toBe(resolveChartFont());
  });
});
