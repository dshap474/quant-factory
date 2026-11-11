/**
 * Cursor-following tooltip positioning and shared surface contract tests.
 *
 * USAGE:
 *   pnpm test -- tooltip.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { withBaseTooltipChrome } from '../../src/charts/core/QfChart';
import {
  containTooltipAtCursor,
  positionEChartsTooltip,
  qfEChartsTooltip,
} from '../../src/charts/core/tooltip';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('qf-charts tooltips', () => {
  it('follows the cursor when there is room', () => {
    expect(containTooltipAtCursor([100, 80], [160, 90], [640, 360])).toEqual([114, 94]);
  });

  it('flips and clamps before leaving the chart container', () => {
    expect(containTooltipAtCursor([620, 345], [160, 90], [640, 360])).toEqual([446, 241]);
    expect(containTooltipAtCursor([2, 2], [160, 90], [640, 360])).toEqual([16, 16]);
  });

  it('uses the same contained cursor behavior for ECharts tooltips', () => {
    expect(
      positionEChartsTooltip([620, 345], null, null, null, {
        contentSize: [160, 90],
        viewSize: [640, 360],
      }),
    ).toEqual([446, 241]);

    expect(
      qfEChartsTooltip({
        axisFontSize: 12,
        tooltipBackground: 'rgb(20 20 20 / 0.94)',
        tooltipBorder: '#555',
        tooltipText: '#fff',
      }),
    ).toMatchObject({
      appendToBody: false,
      backgroundColor: 'var(--qf-chart-tooltip-glass, rgb(20 20 20 / 0.94))',
      borderRadius: 8,
      className: 'qf-echarts-tooltip-host',
      confine: true,
      position: positionEChartsTooltip,
      renderMode: 'html',
      transitionDuration: 0.18,
    });
  });

  it('dresses a raw host tooltip in the qf chrome without touching its behaviour', () => {
    const theme = {
      axisFontSize: 12,
      tooltipBackground: 'rgb(20 20 20)',
      tooltipBorder: '#555',
      tooltipText: '#fff',
    } as Parameters<typeof withBaseTooltipChrome>[1];
    const raw = { tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } } };
    expect(withBaseTooltipChrome(raw, theme).tooltip).toMatchObject({
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: 'var(--qf-chart-tooltip-glass, rgb(20 20 20))',
      className: 'qf-echarts-tooltip-host',
      textStyle: { color: '#fff' },
    });
    expect(withBaseTooltipChrome(raw, theme).tooltip).not.toHaveProperty('position');

    const styled = { tooltip: { backgroundColor: '#000' } };
    expect(withBaseTooltipChrome(styled, theme)).toBe(styled);
    const none = { series: [] };
    expect(withBaseTooltipChrome(none, theme)).toBe(none);
  });
});
