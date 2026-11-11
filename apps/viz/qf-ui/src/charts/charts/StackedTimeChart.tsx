/**
 * Dated stacked areas, bars and overlay lines on one shared, evenly spaced date axis.
 *
 * USAGE:
 *   <StackedTimeChart
 *     ariaLabel="Counts over time"
 *     dates={dates}
 *     series={[
 *       { key: 'a', label: 'Group A', kind: 'area', stack: 'total', values: groupA, step: true },
 *       { key: 'b', label: 'Group B', kind: 'area', stack: 'total', values: groupB, step: true },
 *       { key: 'target', label: 'Target', kind: 'line', values: target, step: true },
 *     ]}
 *     markers={[{ date: dates[40], label: 'change' }]}  // dashed vertical rules
 *     selected={dates.at(-1)}                            // solid vertical rule
 *     onDateClick={(date) => setDay(date)}               // a click anywhere in a date's column
 *   />
 *
 * `dates` and every series' `values` align by index (null is a gap). Series sharing a `stack`
 * id stack; bars of opposite sign stack away from zero. Colours default to the palette in
 * order (series 1 gold). `step` draws held counts as steps. Without `height` the chart takes
 * the package aspect ratio; inside a TimeSeriesChart shell pass `height="100%"`.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { chartTooltipHtml } from '../components/ChartTooltip';
import { QF_CHART_ASPECT_RATIO, QF_CHART_INSET } from '../core/geometry';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { resolveCssColor } from '../theme/tokens';
import { formatTooltipDate } from './timeAxisFormat';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StackedTimeSeries {
  key: string;
  label: string;
  kind: 'area' | 'bar' | 'line';
  /** One value per date; null is a gap. */
  values: readonly (number | null)[];
  /** Series with the same id stack. */
  stack?: string | undefined;
  /** CSS colour; defaults to the palette slot of the series' position. */
  color?: string | undefined;
  /** Step-end joins for held counts (areas and lines). */
  step?: boolean | undefined;
}

export interface StackedTimeMarker {
  date: Date;
  label?: string | undefined;
}

export interface StackedTimeChartProps {
  dates: readonly Date[];
  series: readonly StackedTimeSeries[];
  ariaLabel: string;
  yFormat?: ((value: number) => string) | undefined;
  /** Dashed vertical rules at these dates. */
  markers?: readonly StackedTimeMarker[] | undefined;
  /** Solid vertical rule at this date. */
  selected?: Date | null | undefined;
  /** The clicked date's column, anywhere between the plot's top and bottom. */
  onDateClick?: ((date: Date, index: number) => void) | undefined;
  height?: number | string | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const DEFAULT_FORMAT = (value: number) => value.toLocaleString('en-US');
const HIT_SERIES = '__qf_hit__';
const AREA_OPACITY = 0.55;

function dayKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Per-date positive and negative extents of the drawn values, stacks summed. */
function extents(dates: readonly Date[], series: readonly StackedTimeSeries[]) {
  const high = dates.map(() => 0);
  const low = dates.map(() => 0);
  const stacks = new Map<string, { up: number[]; down: number[] }>();
  for (const item of series) {
    const key = item.stack ?? `__${item.key}`;
    const sums = stacks.get(key) ?? { up: dates.map(() => 0), down: dates.map(() => 0) };
    stacks.set(key, sums);
    item.values.forEach((value, index) => {
      if (value === null || !Number.isFinite(value)) return;
      if (value >= 0) sums.up[index] = (sums.up[index] ?? 0) + value;
      else sums.down[index] = (sums.down[index] ?? 0) + value;
    });
  }
  for (const { up, down } of stacks.values()) {
    up.forEach((value, index) => {
      high[index] = Math.max(high[index] ?? 0, value);
    });
    down.forEach((value, index) => {
      low[index] = Math.min(low[index] ?? 0, value);
    });
  }
  return { high, low };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StackedTimeChart({
  dates,
  series,
  ariaLabel,
  yFormat = DEFAULT_FORMAT,
  markers = [],
  selected = null,
  onDateClick,
  height,
  className,
}: StackedTimeChartProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const labels = dates.map(dayKey);
    const colors = series.map((item, index) =>
      item.color
        ? resolveCssColor(item.color)
        : (theme.palette[index % theme.palette.length] ?? theme.axis),
    );
    const { high, low } = extents(dates, series);
    // ECharts reads bar gaps from the last bar series, so every bar series carries the same
    // pair: hit columns overlap the drawn bars and span the whole band when no bars are drawn.
    const gaps = {
      barGap: '-100%',
      barCategoryGap: series.some((item) => item.kind === 'bar') ? '30%' : 0,
    };
    const peak = Math.max(0, ...high);
    const trough = Math.min(0, ...low);
    const rules = [
      ...markers.map((marker) => ({
        xAxis: dayKey(marker.date),
        lineStyle: { color: theme.axis, type: 'dashed', width: 1, opacity: 0.7 },
        label: { show: Boolean(marker.label), formatter: marker.label ?? '', color: theme.axis },
      })),
      ...(selected
        ? [
            {
              xAxis: dayKey(selected),
              lineStyle: { color: theme.focus, type: 'solid', width: 1 },
              label: { show: false },
            },
          ]
        : []),
    ];
    // Transparent full-height columns take every click, so a date is clickable anywhere.
    const hit = (values: number[], stack: string) => ({
      id: `${HIT_SERIES}${stack}`,
      name: HIT_SERIES,
      type: 'bar',
      stack: `${HIT_SERIES}${stack}`,
      data: values,
      ...gaps,
      itemStyle: { color: 'transparent' },
      emphasis: { disabled: true },
      cursor: onDateClick ? 'pointer' : 'default',
      z: 0,
    });
    const drawn = series.map((item, index) => {
      const color = colors[index];
      const common = {
        id: item.key,
        name: item.label,
        data: item.values.map((value) => (value === null || !Number.isFinite(value) ? '-' : value)),
        stack: item.stack,
        silent: true,
        z: 2,
      };
      if (item.kind === 'bar') {
        return { ...common, ...gaps, type: 'bar', itemStyle: { color } };
      }
      return {
        ...common,
        type: 'line',
        step: item.step ? 'end' : false,
        showSymbol: false,
        lineStyle: { color, width: theme.lineWidth },
        itemStyle: { color },
        ...(item.kind === 'area' ? { areaStyle: { color, opacity: AREA_OPACITY } } : {}),
        z: item.kind === 'line' ? 3 : 2,
      };
    });
    return {
      animation: false,
      grid: { top: QF_CHART_INSET, right: QF_CHART_INSET, bottom: 28, left: 56 },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: series.some((item) => item.kind === 'bar'),
        axisLabel: { color: theme.axis, fontSize: theme.axisFontSize, hideOverlap: true },
        axisLine: { lineStyle: { color: theme.frame, width: 1 } },
        axisTick: { show: false },
        axisPointer: {
          type: 'line',
          lineStyle: { color: theme.crosshair, width: 1, type: [4, 4] },
        },
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: theme.axis,
          fontSize: theme.axisFontSize,
          formatter: (value: number) => yFormat(value),
        },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: theme.grid, opacity: theme.gridOpacity, width: 1 } },
      },
      tooltip: {
        ...qfEChartsTooltip(theme, 11),
        trigger: 'axis',
        formatter: (params: unknown) => {
          const rows = (Array.isArray(params) ? params : [params]) as {
            dataIndex?: number;
            seriesName?: string;
            seriesIndex?: number;
          }[];
          const index = rows[0]?.dataIndex;
          const date = index === undefined ? undefined : dates[index];
          if (!date || index === undefined) return '';
          return chartTooltipHtml({
            date: formatTooltipDate(date),
            items: series.flatMap((item, at) => {
              const value = item.values[index];
              if (value === null || value === undefined || !Number.isFinite(value)) return [];
              return [{ label: item.label, value: yFormat(value), swatch: colors[at] ?? '' }];
            }),
          });
        },
      },
      series: [
        {
          ...hit(
            dates.map(() => peak),
            'up',
          ),
          markLine: { silent: true, symbol: 'none', data: rules },
        },
        ...(trough < 0
          ? [
              hit(
                dates.map(() => trough),
                'down',
              ),
            ]
          : []),
        ...drawn,
      ],
      aria: { enabled: true, decal: { show: false } },
    };
  }, [dates, markers, onDateClick, selected, series, theme, yFormat]);

  const chart = (
    <QfChart
      option={option}
      ariaLabel={ariaLabel}
      height={height ?? '100%'}
      className={className}
      interactive={Boolean(onDateClick)}
      onClick={(params) => {
        const index = params.dataIndex;
        const date = typeof index === 'number' ? dates[index] : undefined;
        if (date && typeof index === 'number') onDateClick?.(date, index);
      }}
    />
  );
  if (height != null) return chart;
  return <div style={{ aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` }}>{chart}</div>;
}
