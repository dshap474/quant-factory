/**
 * Horizontal bars comparing named categories, one or more series per category.
 *
 * USAGE:
 *   <CategoryBars
 *     categories={['Market', 'Maker']}
 *     series={[{ name: 'Saving', values: [0, 1.7] }]}
 *     unit=" bps"
 *     height={240}
 *   />
 *
 * Categories read top to bottom in the order given. A null value draws no bar.
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

export interface CategoryBarsSeries {
  name: string;
  values: readonly (number | null)[];
}

export interface CategoryBarsProps {
  categories: readonly string[];
  series: readonly CategoryBarsSeries[];
  height: number | string;
  /** Appended to every value in labels and tooltips, for example ` bps`. */
  unit?: string;
  digits?: number;
  ariaLabel?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CategoryBars({
  categories,
  series,
  height,
  unit = '',
  digits = 2,
  ariaLabel = 'Category comparison',
}: CategoryBarsProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const format = (value: number) => `${value.toFixed(digits)}${unit}`;
    const tooltip = (params: unknown): string => {
      const rows = (Array.isArray(params) ? params : [params]) as Array<{
        name?: string;
        seriesName?: string;
        value?: unknown;
      }>;
      return chartTooltipHtml({
        date: rows[0]?.name ?? '',
        items: rows
          .filter((row) => typeof row.value === 'number')
          .map((row) => ({ label: row.seriesName ?? '', value: format(row.value as number) })),
      });
    };
    return {
      animation: false,
      legend:
        series.length > 1
          ? { top: 0, textStyle: { color: theme.axis, fontSize: theme.axisFontSize } }
          : undefined,
      grid: { top: series.length > 1 ? 28 : 8, right: 16, bottom: 4, left: 8, containLabel: true },
      xAxis: {
        type: 'value',
        splitNumber: 4,
        axisLabel: { color: theme.axis, fontSize: theme.axisFontSize },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          show: true,
          lineStyle: { color: theme.grid, opacity: theme.gridOpacity, type: 'solid', width: 1 },
        },
      },
      yAxis: {
        type: 'category',
        inverse: true,
        data: [...categories],
        axisLabel: { color: theme.axis, fontSize: theme.axisFontSize, interval: 0 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'axis',
        axisPointer: { type: 'shadow', shadowStyle: { color: theme.grid, opacity: 0.5 } },
        formatter: tooltip,
      },
      series: series.map((row, index) => ({
        type: 'bar' as const,
        name: row.name,
        data: [...row.values],
        itemStyle: {
          color: theme.palette[index % theme.palette.length],
          borderRadius: 2,
        },
        barMaxWidth: 14,
      })),
    };
  }, [categories, digits, series, theme, unit]);
  return <QfChart option={option} height={height} ariaLabel={ariaLabel} />;
}
