/**
 * Caller-sized compact histogram.
 *
 * Axis-free by default so it can sit inline as a sparkline-sized glyph; pass
 * `axes` when the histogram is rendered large inside a framed chart and the
 * reader expects a real value scale.
 *
 * USAGE:
 *   <Histogram values={[2, 4]} labels={['A', 'B']} height={80} />
 *   <Histogram values={[2, 4]} labels={['A', 'B']} height={160} axes />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { chartTooltipHtml } from '../components/ChartTooltip';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface HistogramProps {
  values: readonly number[];
  labels: readonly string[];
  height: number | string;
  ariaLabel?: string;
  /** Show a gridlined y value scale. Off by default (compact glyph shape). */
  axes?: boolean;
}

// --------------------------------------------------------------------------- #
// Tooltip
// --------------------------------------------------------------------------- #

/** The bin label heads the tooltip the way a date heads a time-series tooltip. */
function histogramTooltipHtml(params: unknown): string {
  const first = (Array.isArray(params) ? params[0] : params) as
    | { name?: string; value?: unknown }
    | undefined;
  const value = Number(first?.value);
  if (!first || !Number.isFinite(value)) return '';
  return chartTooltipHtml({
    date: first.name ?? '',
    items: [{ label: 'Count', value: value.toLocaleString() }],
  });
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Histogram({
  values,
  labels,
  height,
  ariaLabel = 'Value histogram',
  axes = false,
}: HistogramProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(
    () => ({
      animation: false,
      grid: axes
        ? { top: 8, right: 6, bottom: 6, left: 36 }
        : { top: 3, right: 2, bottom: 3, left: 2 },
      xAxis: { type: 'category', show: false, data: labels },
      yAxis: axes
        ? {
            type: 'value',
            show: true,
            splitNumber: 3,
            axisLabel: { color: theme.axis, fontSize: theme.axisFontSize },
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: {
              show: true,
              lineStyle: {
                color: theme.grid,
                opacity: theme.gridOpacity,
                type: 'solid',
                width: 1,
              },
            },
          }
        : { type: 'value', show: false },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: theme.grid, opacity: 0.5 } },
        formatter: histogramTooltipHtml,
      },
      series: [
        {
          type: 'bar',
          data: values,
          itemStyle: { color: theme.palette[0], borderRadius: [2, 2, 0, 0] },
          barCategoryGap: '8%',
        },
      ],
    }),
    [axes, labels, theme, values],
  );
  return <QfChart option={option} height={height} ariaLabel={ariaLabel} />;
}
