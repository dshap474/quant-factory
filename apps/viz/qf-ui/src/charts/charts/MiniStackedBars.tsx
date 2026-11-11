/**
 * Caller-sized axis-free stacked columns: a sparkline for counts by category (runs per
 * day by outcome, say). Hover shows each column's label and values.
 *
 * USAGE:
 *   <MiniStackedBars
 *     ariaLabel="Runs per day, 14 days"
 *     labels={days}
 *     series={[
 *       { key: 'ok', label: 'Succeeded', values: ok },
 *       { key: 'bad', label: 'Failed', values: bad },
 *     ]}
 *     height={24}
 *     width={112}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { chartTooltipHtml } from '../components/ChartTooltip';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { resolveCssColor } from '../theme/tokens';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface MiniStackedBarsSeries {
  key: string;
  label: string;
  /** CSS colour; defaults to the palette slot of the series' position. */
  color?: string | undefined;
  /** One value per label. */
  values: readonly number[];
}

export interface MiniStackedBarsProps {
  labels: readonly string[];
  series: readonly MiniStackedBarsSeries[];
  ariaLabel: string;
  height: number | string;
  /** Defaults to the container width. */
  width?: number | string | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MiniStackedBars({
  labels,
  series,
  ariaLabel,
  height,
  width,
  className,
}: MiniStackedBarsProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const colors = series.map((item, index) =>
      item.color
        ? resolveCssColor(item.color)
        : (theme.palette[index % theme.palette.length] ?? theme.axis),
    );
    const totals = labels.map((_, index) =>
      series.reduce((sum, item) => sum + (item.values[index] ?? 0), 0),
    );
    return {
      animation: false,
      grid: { top: 1, right: 0, bottom: 1, left: 0 },
      xAxis: { type: 'category', show: false, data: [...labels] },
      // A fixed floor keeps a one-run day from filling the whole height.
      yAxis: { type: 'value', show: false, min: 0, max: Math.max(4, ...totals) },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'axis',
        axisPointer: { type: 'none' },
        formatter: (params: unknown) => {
          const index = (Array.isArray(params) ? params[0] : params)?.dataIndex as
            | number
            | undefined;
          if (index === undefined) return '';
          return chartTooltipHtml({
            date: labels[index] ?? '',
            items: series.map((item, at) => ({
              label: item.label,
              value: (item.values[index] ?? 0).toLocaleString('en-US'),
              swatch: colors[at] ?? '',
            })),
          });
        },
      },
      series: [
        // An empty day still shows a faint stub so the strip reads as a timeline.
        {
          id: '__base__',
          type: 'bar',
          stack: 'all',
          data: totals.map((total) => (total === 0 ? 0.25 : 0)),
          itemStyle: { color: theme.frame, opacity: 0.6 },
          barCategoryGap: '25%',
          silent: true,
        },
        ...series.map((item, index) => ({
          id: item.key,
          name: item.label,
          type: 'bar',
          stack: 'all',
          data: [...item.values],
          itemStyle: { color: colors[index] },
          barCategoryGap: '25%',
        })),
      ],
    };
  }, [labels, series, theme]);
  return (
    <QfChart
      option={option}
      ariaLabel={ariaLabel}
      height={height}
      width={width}
      className={className}
    />
  );
}
