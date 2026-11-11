/**
 * Package-owned time-series line renderer with benchmark and visibility semantics.
 *
 * USAGE:
 *   <LineChart series={series} hiddenSeries={hidden} height={320} />
 *
 * Hovering a legend row (emphasizedSeries) eases the other series down; pointing at the
 * plot never focuses a series.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { chartTooltipHtml } from '../components/ChartTooltip';
import {
  linkedPaneGrid,
  PANE_LABEL_MARGIN,
  showsSharedAxis,
  useMultiPaneLink,
} from '../components/MultiPaneContext';
import {
  axisNameBand,
  axisNameThickness,
  QF_CHART_INSET,
  QF_CHART_LABEL_GAP,
  QF_CHART_RULE_WIDTH,
} from '../core/geometry';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { chartColor } from '../theme/chartColor';
import { resolveCssColor } from '../theme/tokens';
import type { QfPadding, QfPoint, QfSeries } from '../types/contracts';
import { axisLabelWidth, extremeLabelVisibility } from './axisLabelWidth';
import {
  echartsInterpolation,
  type QfInterpolation,
  type QfLegacyCurve,
  resolveInterpolation,
} from './interpolation';
import { decimateLineData, type QfLineDatum } from './lineDecimation';
import { formatQfValue } from './qfValueFormat';
import { formatTimeTick, formatTooltipDate } from './timeAxisFormat';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface QfLinePoint extends QfPoint {}

export interface QfAreaGradientStop {
  offset: number;
  color: string;
}

export interface QfAreaGradient {
  stops: readonly QfAreaGradientStop[];
}

export interface QfLineSeries extends QfSeries {
  points: readonly QfLinePoint[];
  area?: boolean;
  areaColor?: string | QfAreaGradient;
  areaOpacity?: number;
  /** `zero` fills from the value axis origin; `range` (default) fills from the axis edge. */
  areaBaseline?: 'range' | 'zero';
  /** @deprecated use interpolation; `interpolation` wins when both are set. */
  curve?: QfLegacyCurve;
  /** How this line joins its points; overrides the chart's `interpolation`. */
  interpolation?: QfInterpolation;
  defined?: (point: QfLinePoint) => boolean;
  opacity?: number;
  /**
   * `false` draws the area fill alone with no stroke. Every drawn line is
   * QF_CHART_LINE_WIDTH wide; there is no per-series width.
   */
  showLine?: boolean;
  /** Trade arrows on this line: green buys point up from below the value, red sells down from above. */
  marks?: readonly QfLineMark[];
}

/** One trade on a line: its time, the line's value there, and its direction. */
export interface QfLineMark {
  date: Date;
  value: number;
  side: 'buy' | 'sell';
}

/** Shaded time interval drawn behind every series (an evaluation window, a holdout). */
export interface QfXBand {
  from: Date;
  to: Date;
  color: string;
  opacity?: number;
}

export interface LineChartProps {
  series: readonly QfLineSeries[];
  /** Explicit height; omit to let the package apply its default chart aspect ratio. */
  height?: number | string;
  ariaLabel?: string;
  className?: string;
  hiddenSeries?: ReadonlySet<string>;
  xDomain?: readonly [Date, Date];
  /** Time-axis ticks and built-in tooltip clock; local preserves the existing default. */
  timeZone?: 'local' | 'utc';
  yDomain?: readonly [number, number];
  ySecondaryDomain?: readonly [number, number];
  yTertiaryDomain?: readonly [number, number];
  benchmarkDomain?: readonly [number, number];
  /**
   * `own` (default) autoscales benchmarks on their hidden axis. `primary` indexes each
   * benchmark to the first primary series at the first visible time and gives both axes
   * one domain spanning the primary series and the indexed benchmark, so the benchmark's
   * returns read on the primary scale and it is never clipped. `shared` keeps already
   * comparable values unchanged on the primary axis (portfolio NAV and drawdown).
   */
  benchmarkScale?: 'own' | 'primary' | 'shared';
  yScaleType?: 'linear' | 'log';
  benchmarkScaleType?: 'linear' | 'log';
  yAxisInverse?: boolean;
  ySecondaryAxisInverse?: boolean;
  ySplitNumber?: number;
  yFormat?: (value: number) => string;
  ySecondaryFormat?: (value: number) => string;
  yTertiaryFormat?: (value: number) => string;
  yAxisName?: string;
  ySecondaryAxisName?: string;
  yTertiaryAxisName?: string;
  thresholdY?: number;
  /** Dashed vertical reference line at this time (where a backtest ends and paper begins). */
  thresholdX?: Date;
  /** Background bands; memoize the array so series data is not re-mapped on every render. */
  xBands?: readonly QfXBand[];
  padding?: QfPadding;
  tooltipHtml?: (date: Date) => string;
  tooltip?: boolean;
  preservePlotGeometry?: boolean;
  showXAxis?: boolean;
  showYAxis?: boolean;
  showYAxisLabels?: boolean;
  emphasizedSeries?: string | null;
  visibleSecondaryAxis?: boolean;
  visibleTertiaryAxis?: boolean;
  /** How every line joins its points unless a series sets its own; linear by default. */
  interpolation?: QfInterpolation;
}

const EMPTY_HIDDEN = new Set<string>();
const DEFAULT_PADDING = { top: 20, right: 20, bottom: 40, left: 70 };
const DEFAULT_FORMAT = (value: number) => String(value);
const DIM_OPACITY = 0.25;
/** Focus changes fade the other lines over this many milliseconds. */
const FOCUS_FADE_MS = 160;
// Each fade frame restyles every series (~25 ms per chart at ~125k points), so past this
// many drawn points the fade would stutter; focus then snaps in one restyle instead.
const FOCUS_FADE_MAX_POINTS = 20_000;
const BENCHMARK_OPACITY = 0.72;
/** Headroom around a shared benchmark domain, as a share of the plotted range. */
const SHARED_DOMAIN_PAD = 0.05;
const BAND_OPACITY = 0.08;
/** Linked panes are short, so three value ticks keep the labels from crowding. */
const LINKED_Y_SPLIT_NUMBER = 3;
/**
 * Diameter of the hover dots. ECharts centres the 2px surface ring on the edge, so 10
 * leaves an 8px coloured dot inside a 12px mark (Lightweight Charts r4 + 2px border).
 */
const POINT_DOT_SIZE = 10;
const POINT_DOT_RING = 2;
/** The zero line reads as the axis origin: solid and brighter than the grid. */
const ZERO_LINE_OPACITY = 0.9;
/** Minimum horizontal clearance between two visible time-axis labels, in pixels. */
const TIME_LABEL_MIN_GAP = 12;
/** 4px dash, 4px gap: the --qf-chart-crosshair-dash rhythm the SVG and pane crosshairs use. */
const CROSSHAIR_DASH = [4, 4];
/** Above ECharts' marker lines (z 5), below the axis pointer and tooltip (z 50). */
const SERIES_Z = 6;
const MARK_SIZE = 8;
/** Clear of the line: half the arrow plus a pixel of air. */
const MARK_OFFSET = MARK_SIZE / 2 + 1;

// --------------------------------------------------------------------------- #
// Model
// --------------------------------------------------------------------------- #

export interface QfLineModel {
  legend: readonly QfLineSeries[];
  plotted: readonly QfLineSeries[];
}

export function normalizeLineSeries(
  series: readonly QfLineSeries[],
  hiddenSeries: ReadonlySet<string> = EMPTY_HIDDEN,
): QfLineModel {
  return {
    legend: series,
    plotted: series.filter((item) => !hiddenSeries.has(item.key)),
  };
}

export function axisIndexForSeries(
  series: QfLineSeries,
  hasNonBenchmarkSecondary = false,
  hasNonBenchmarkTertiary = false,
): number {
  if (series.isBenchmark)
    return 1 + Number(hasNonBenchmarkSecondary) + Number(hasNonBenchmarkTertiary);
  if (series.axis === 'tertiary') return hasNonBenchmarkSecondary ? 2 : 1;
  return series.axis === 'secondary' ? 1 : 0;
}

function tooltipDate(params: unknown): Date | null {
  if (!Array.isArray(params)) return null;
  const first = params[0] as { value?: unknown } | undefined;
  if (!Array.isArray(first?.value)) return null;
  const timestamp = Number(first.value[0]);
  return Number.isFinite(timestamp) ? new Date(timestamp) : null;
}

/** Value range of the primary axis: the caller's domain, else the plotted extent. */
export function primaryValueDomain(
  plotted: readonly QfLineSeries[],
  yDomain: readonly [number, number] | undefined,
): readonly [number, number] | null {
  if (yDomain) return yDomain;
  const hasNonBenchmarkSecondary = plotted.some(
    (item) => item.axis === 'secondary' && !item.isBenchmark,
  );
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const item of plotted) {
    if (axisIndexForSeries(item, hasNonBenchmarkSecondary) !== 0) continue;
    for (const point of item.points) {
      if (point.value == null || !Number.isFinite(point.value)) continue;
      min = Math.min(min, point.value);
      max = Math.max(max, point.value);
    }
  }
  return Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null;
}

/** The primary range widened to every indexed benchmark, so a shared scale clips nothing. */
function sharedValueDomain(plotted: readonly QfLineSeries[]): readonly [number, number] | null {
  let [min, max] = primaryValueDomain(plotted, undefined) ?? [
    Number.POSITIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
  ];
  for (const item of plotted) {
    if (!item.isBenchmark) continue;
    for (const point of item.points) {
      if (!plottedValue(point)) continue;
      min = Math.min(min, point.value);
      max = Math.max(max, point.value);
    }
  }
  return Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null;
}

const plottedValue = (point: QfLinePoint): point is QfLinePoint & { value: number } =>
  point.value != null && Number.isFinite(point.value);

/** The value at or before `time`: the series' last plotted point not after it. */
function valueAt(points: readonly QfLinePoint[], time: number): number | null {
  let value: number | null = null;
  for (const point of points) {
    if (point.date.getTime() > time) break;
    if (plottedValue(point)) value = point.value;
  }
  return value;
}

/**
 * Rebase each benchmark onto the primary series that starts first (from `from` on):
 * both start together and the benchmark takes that series' value there, so equal
 * returns sit at equal heights. Benchmark points before the shared start are dropped.
 */
export function indexBenchmarksToPrimary(
  plotted: readonly QfLineSeries[],
  from?: Date,
): readonly QfLineSeries[] {
  const after = from?.getTime() ?? Number.NEGATIVE_INFINITY;
  const firstTime = (item: QfLineSeries) =>
    item.points
      .find((point) => plottedValue(point) && point.date.getTime() >= after)
      ?.date.getTime();
  const anchor = plotted
    .filter((item) => !item.isBenchmark && (item.axis ?? 'primary') === 'primary')
    .map((item) => ({ item, time: firstTime(item) }))
    .filter((entry): entry is { item: QfLineSeries; time: number } => entry.time !== undefined)
    .sort((left, right) => left.time - right.time)[0];
  if (!anchor) return plotted;
  return plotted.map((item) => {
    if (!item.isBenchmark) return item;
    const own = firstTime(item);
    if (own === undefined) return { ...item, points: [] };
    const start = Math.max(own, anchor.time);
    const base = valueAt(item.points, start);
    const level = valueAt(anchor.item.points, start);
    if (base == null || level == null || base === 0) return { ...item, points: [] };
    return {
      ...item,
      points: item.points
        .filter((point) => point.date.getTime() >= start)
        .map((point) =>
          plottedValue(point) ? { ...point, value: (point.value * level) / base } : point,
        ),
    };
  });
}

/** The primary data range with headroom; ratio headroom on a log scale keeps it positive. */
function paddedDomain(
  domain: readonly [number, number] | null,
  scale: 'linear' | 'log',
): readonly [number, number] | undefined {
  if (!domain) return undefined;
  const [min, max] = domain;
  if (scale === 'log') return [min / (1 + SHARED_DOMAIN_PAD), max * (1 + SHARED_DOMAIN_PAD)];
  const pad = (max - min) * SHARED_DOMAIN_PAD || Math.abs(max) * SHARED_DOMAIN_PAD || 1;
  return [min - pad, max + pad];
}

function areaColor(color: string | QfAreaGradient): string | Record<string, unknown> {
  if (typeof color === 'string') return resolveCssColor(color);
  return {
    type: 'linear',
    x: 0,
    y: 0,
    x2: 1,
    y2: 0,
    colorStops: color.stops.map((stop) => ({
      offset: stop.offset,
      color: resolveCssColor(stop.color),
    })),
    global: false,
  };
}

// --------------------------------------------------------------------------- #
// Focus fade
// --------------------------------------------------------------------------- #

// Each series' opacity multiplier eases from where it is toward 1 (focused, or no focus)
// or DIM_OPACITY. Without matchMedia (jsdom), under reduced motion, or when `fade` is off
// (a heavy chart) it jumps instead.
function useFocusFade(
  ids: readonly string[],
  target: string | null,
  fade: boolean,
): ReadonlyMap<string, number> {
  const [levels, setLevels] = useState<ReadonlyMap<string, number>>(() => new Map());
  const levelsRef = useRef(levels);
  const idsKey = ids.join('\u0000');
  useEffect(() => {
    const ids = idsKey ? idsKey.split('\u0000') : [];
    const goal = new Map(ids.map((id) => [id, target == null || id === target ? 1 : DIM_OPACITY]));
    const from = new Map(ids.map((id) => [id, levelsRef.current.get(id) ?? 1]));
    const commit = (next: ReadonlyMap<string, number>) => {
      levelsRef.current = next;
      setLevels(next);
    };
    const animates =
      fade &&
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!animates) {
      commit(goal);
      return;
    }
    if (ids.every((id) => from.get(id) === goal.get(id))) return;
    const start = performance.now();
    let frame = 0;
    let scheduling = false;
    // A frame that fires synchronously (test shims) jumps straight to the goal.
    const schedule = () => {
      scheduling = true;
      frame = window.requestAnimationFrame(step);
      scheduling = false;
    };
    const step = (now: number) => {
      if (scheduling) {
        commit(goal);
        return;
      }
      const progress = Math.min(1, (now - start) / FOCUS_FADE_MS);
      const eased = 1 - (1 - progress) ** 3;
      commit(
        new Map(
          ids.map((id) => {
            const a = from.get(id) ?? 1;
            const b = goal.get(id) ?? 1;
            return [id, a + (b - a) * eased];
          }),
        ),
      );
      if (progress < 1) schedule();
    };
    schedule();
    return () => window.cancelAnimationFrame(frame);
  }, [idsKey, target, fade]);
  return levels;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function LineChart({
  series,
  height,
  ariaLabel = 'Time series chart',
  className,
  hiddenSeries = EMPTY_HIDDEN,
  xDomain,
  timeZone = 'local',
  yDomain: callerYDomain,
  ySecondaryDomain,
  yTertiaryDomain,
  benchmarkDomain,
  benchmarkScale = 'own',
  yScaleType = 'linear',
  benchmarkScaleType = 'linear',
  yAxisInverse = false,
  ySecondaryAxisInverse = false,
  ySplitNumber,
  yFormat,
  ySecondaryFormat,
  yTertiaryFormat,
  yAxisName,
  ySecondaryAxisName,
  yTertiaryAxisName,
  thresholdY,
  thresholdX,
  xBands,
  padding = DEFAULT_PADDING,
  tooltipHtml,
  tooltip = true,
  preservePlotGeometry = false,
  showXAxis = true,
  showYAxis = true,
  showYAxisLabels = showYAxis,
  emphasizedSeries = null,
  visibleSecondaryAxis,
  visibleTertiaryAxis,
  interpolation,
}: LineChartProps) {
  const theme = useChartTheme();
  // Inside a linked multi-pane stack the shell owns the geometry: fixed gutters, one
  // shared time axis on the bottom pane, and a domain every pane plots against.
  const link = useMultiPaneLink();
  const linkedGrid = useMemo(() => (link ? linkedPaneGrid(link) : null), [link]);
  const drawsTimeAxis = showXAxis && (link ? showsSharedAxis(link.position) : true);
  const dividesBelow = Boolean(link) && !drawsTimeAxis;
  const resolvedXDomain = xDomain ?? link?.xDomain ?? undefined;
  const resolvedYSplitNumber = ySplitNumber ?? (link ? LINKED_Y_SPLIT_NUMBER : undefined);
  // A stack that renders one tooltip for every pane turns the per-pane tooltip off.
  const drawsTooltip = tooltip && !link?.shellTooltip;
  const sharesScale = benchmarkScale !== 'own';
  const model = useMemo(() => {
    const normalized = normalizeLineSeries(series, hiddenSeries);
    return benchmarkScale === 'primary'
      ? {
          ...normalized,
          plotted: indexBenchmarksToPrimary(normalized.plotted, resolvedXDomain?.[0]),
        }
      : normalized;
  }, [hiddenSeries, resolvedXDomain, series, benchmarkScale]);
  // A shared benchmark scale needs one explicit domain on both value axes.
  const yDomain = useMemo(
    () =>
      callerYDomain ??
      (sharesScale && model.plotted.some((item) => item.isBenchmark)
        ? paddedDomain(sharedValueDomain(model.plotted), yScaleType)
        : undefined),
    [callerYDomain, model.plotted, sharesScale, yScaleType],
  );
  // `QfSeries.valueFormat` is the series' own value-to-text rule: it renders that
  // series' tooltip row and, when the caller supplied no axis formatter, the value
  // labels of the axis the series is plotted against.
  const axisFormatters = useMemo(() => {
    const formatterFor = (axis: 'primary' | 'secondary' | 'tertiary') => {
      const owner = model.plotted.find(
        (item) =>
          !item.isBenchmark && (item.axis ?? 'primary') === axis && item.valueFormat !== undefined,
      );
      const format = owner?.valueFormat;
      if (format === undefined) return null;
      return (value: number) => formatQfValue(value, format);
    };
    return {
      primary: formatterFor('primary'),
      secondary: formatterFor('secondary'),
      tertiary: formatterFor('tertiary'),
    };
  }, [model.plotted]);
  const resolvedYFormat = yFormat ?? axisFormatters.primary ?? DEFAULT_FORMAT;
  const resolvedYSecondaryFormat = ySecondaryFormat ?? axisFormatters.secondary ?? DEFAULT_FORMAT;
  const resolvedYTertiaryFormat = yTertiaryFormat ?? axisFormatters.tertiary ?? DEFAULT_FORMAT;
  const seriesTooltipHtml = useCallback(
    (params: unknown) => {
      if (!Array.isArray(params) || params.length === 0) return '';
      const date = tooltipDate(params);
      const items = params.flatMap((entry) => {
        const row = (entry ?? {}) as {
          color?: unknown;
          seriesId?: string;
          seriesName?: string;
          value?: unknown;
        };
        const value = Array.isArray(row.value) ? Number(row.value[1]) : Number.NaN;
        if (!Number.isFinite(value)) return [];
        const source = model.plotted.find((item) => item.key === row.seriesId);
        return [
          {
            label: source?.label ?? row.seriesName ?? '',
            value: formatQfValue(value, source?.valueFormat),
            ...(typeof row.color === 'string' ? { swatch: row.color } : {}),
          },
        ];
      });
      if (items.length === 0) return '';
      return chartTooltipHtml({ date: formatTooltipDate(date ?? new Date(), timeZone), items });
    },
    [model.plotted, timeZone],
  );
  // Linked panes report how wide their value labels run so the stack can size one gutter
  // that fits every pane; the widest pane wins and the axes line up. A rotated value-axis
  // name adds its own band to that gutter and is placed from the same measurement.
  const requestLeftInset = link?.requestLeftInset;
  const labelWidth = useMemo(() => {
    if ((!requestLeftInset && !yAxisName) || !showYAxisLabels) return 0;
    return axisLabelWidth({
      domain: primaryValueDomain(model.plotted, yDomain),
      scale: yScaleType,
      splitNumber: resolvedYSplitNumber ?? LINKED_Y_SPLIT_NUMBER,
      format: resolvedYFormat,
      fontSize: theme.axisFontSize,
    });
  }, [
    model.plotted,
    requestLeftInset,
    yAxisName,
    resolvedYSplitNumber,
    showYAxisLabels,
    resolvedYFormat,
    theme.axisFontSize,
    yDomain,
    yScaleType,
  ]);
  const nameBand = yAxisName ? axisNameBand(theme.axisFontSize) : 0;
  useEffect(() => {
    requestLeftInset?.(labelWidth + nameBand);
  }, [labelWidth, nameBand, requestLeftInset]);
  // The name's outer edge sits on the card inset: in a stack at the shared gutter's edge,
  // otherwise one label gap beyond the measured value labels.
  const yAxisNameGap = linkedGrid
    ? linkedGrid.left - QF_CHART_INSET - axisNameThickness(theme.axisFontSize)
    : Math.ceil(labelWidth) + QF_CHART_LABEL_GAP * 2;
  const effectiveXDomain = useMemo<readonly [Date, Date] | null>(() => {
    if (resolvedXDomain) return resolvedXDomain;
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const item of model.plotted) {
      for (const point of item.points) {
        const timestamp = point.date.getTime();
        if (!Number.isFinite(timestamp)) continue;
        min = Math.min(min, timestamp);
        max = Math.max(max, timestamp);
      }
    }
    return Number.isFinite(min) && Number.isFinite(max) ? [new Date(min), new Date(max)] : null;
  }, [model.plotted, resolvedXDomain]);
  // Focus changes repaint on every pointer enter/leave and fade frame, so per-point
  // series data and the static option skeleton are memoized separately below; hover
  // re-tints series styles without re-mapping point data or rebuilding axes.
  const baseSeries = useMemo(() => {
    const hasNonBenchmarkSecondary = model.plotted.some(
      (item) => item.axis === 'secondary' && !item.isBenchmark,
    );
    const hasNonBenchmarkTertiary = model.plotted.some(
      (item) => item.axis === 'tertiary' && !item.isBenchmark,
    );
    const primaryIndex = model.plotted.findIndex(
      (item) => axisIndexForSeries(item, hasNonBenchmarkSecondary, hasNonBenchmarkTertiary) === 0,
    );
    const primaryDomain = primaryValueDomain(model.plotted, yDomain);
    const drawsZeroLine =
      yScaleType === 'linear' &&
      primaryDomain != null &&
      Math.min(...primaryDomain) < 0 &&
      Math.max(...primaryDomain) > 0 &&
      thresholdY !== 0;
    const referenceLines = [
      ...(drawsZeroLine
        ? [
            {
              yAxis: 0,
              lineStyle: {
                color: theme.frame,
                type: 'solid',
                opacity: ZERO_LINE_OPACITY,
                width: QF_CHART_RULE_WIDTH,
              },
            },
          ]
        : []),
      ...(thresholdY != null ? [{ yAxis: thresholdY }] : []),
      ...(thresholdX != null ? [{ xAxis: thresholdX.getTime() }] : []),
    ];
    return model.plotted.map((item, index) => {
      const color = item.isBenchmark
        ? theme.benchmark
        : resolveCssColor(item.color ?? theme.palette[index % theme.palette.length] ?? theme.axis);
      const opacity = item.isBenchmark
        ? Math.min(item.opacity ?? BENCHMARK_OPACITY, BENCHMARK_OPACITY)
        : (item.opacity ?? 1);
      const lineStyle = {
        color,
        opacity,
        type: item.isBenchmark ? 'dashed' : 'solid',
        width: item.showLine === false ? 0 : theme.lineWidth,
        cap: 'round',
        join: 'round',
      };
      const areaStyle = item.area
        ? {
            color: areaColor(item.areaColor ?? color),
            opacity: item.areaOpacity ?? Math.min(opacity, 0.3),
            // ECharts `auto` fills from the nearer axis extent, so an all-positive
            // series would fill from the axis edge; a zero baseline is numeric.
            origin: item.areaBaseline === 'zero' ? 0 : 'auto',
          }
        : undefined;
      return {
        id: item.key,
        name: item.label,
        type: 'line',
        // Marker lines take their z from ECharts' shared markLine component (5), not the
        // series option, so the strokes rise above it: the zero and reference lines sit
        // under the data like the grid does instead of cutting across it.
        z: SERIES_Z,
        yAxisIndex:
          item.isBenchmark && benchmarkScale === 'shared'
            ? 0
            : axisIndexForSeries(item, hasNonBenchmarkSecondary, hasNonBenchmarkTertiary),
        // Thinned to a fixed bucket count, not ECharts' pixel-width `sampling`, so the
        // value-axis extent (and every y label) holds still when the plot resizes.
        data: decimateLineData(
          item.points.map(
            (point): QfLineDatum => [
              point.date.getTime(),
              point.value == null || !(item.defined?.(point) ?? point.active !== false)
                ? '-'
                : point.value,
            ],
          ),
        ),
        // Symbols stay hidden until the axis pointer lands on a point; the emphasis state
        // then draws that point as a dot ringed in the chart surface.
        showSymbol: item.points.length === 1,
        symbol: item.points.length === 1 || !item.isBenchmark ? 'circle' : 'none',
        symbolSize: item.points.length === 1 ? 7 : POINT_DOT_SIZE,
        ...echartsInterpolation(
          resolveInterpolation(item.interpolation, interpolation, item.curve),
        ),
        connectNulls: false,
        lineStyle,
        // Pointing at a line puts its series in ECharts' emphasis state; a partial
        // emphasis style drops the stroke, so it repeats the normal one. Dimming the
        // other lines is the focus fade's job, not ECharts' emphasis.
        emphasis: {
          focus: 'none',
          scale: false,
          lineStyle,
          areaStyle,
          itemStyle: { borderColor: theme.background, borderWidth: POINT_DOT_RING },
        },
        itemStyle: { color, opacity },
        areaStyle,
        markLine:
          index === primaryIndex && referenceLines.length > 0
            ? {
                silent: true,
                symbol: 'none',
                animation: false,
                lineStyle: {
                  color: theme.frame,
                  type: 'dashed',
                  opacity: 0.65,
                  width: QF_CHART_RULE_WIDTH,
                },
                // ECharts widens an emphasised marker line to 3px; rules never thicken.
                emphasis: { disabled: true },
                label: { show: false },
                data: referenceLines,
              }
            : undefined,
        // Always an object while the series has `marks`, even an empty one: the chart merges
        // updates, so dropping markPoint would leave the previous arrows on screen.
        markPoint: item.marks
          ? {
              silent: true,
              animation: false,
              symbol: 'triangle',
              symbolSize: MARK_SIZE,
              label: { show: false },
              emphasis: { disabled: true },
              data: item.marks.map((mark) => ({
                coord: [mark.date.getTime(), mark.value],
                symbolRotate: mark.side === 'sell' ? 180 : 0,
                symbolOffset: [0, mark.side === 'sell' ? -MARK_OFFSET : MARK_OFFSET],
                itemStyle: {
                  color: resolveCssColor(chartColor(mark.side === 'buy' ? 'positive' : 'negative')),
                  opacity,
                },
              })),
            }
          : undefined,
        markArea:
          index === 0 && xBands && xBands.length > 0
            ? {
                silent: true,
                label: { show: false },
                data: xBands.map((band) => [
                  {
                    xAxis: band.from.getTime(),
                    itemStyle: {
                      color: resolveCssColor(band.color),
                      opacity: band.opacity ?? BAND_OPACITY,
                    },
                  },
                  { xAxis: band.to.getTime() },
                ]),
              }
            : undefined,
      };
    });
  }, [
    benchmarkScale,
    interpolation,
    model.plotted,
    theme,
    thresholdX,
    thresholdY,
    xBands,
    yDomain,
    yScaleType,
  ]);
  const baseOption = useMemo<QfChartOption>(() => {
    const hasNonBenchmarkSecondary = model.plotted.some(
      (item) => item.axis === 'secondary' && !item.isBenchmark,
    );
    const hasNonBenchmarkTertiary = model.plotted.some(
      (item) => item.axis === 'tertiary' && !item.isBenchmark,
    );
    const hasBenchmark =
      benchmarkScale !== 'shared' && model.plotted.some((item) => item.isBenchmark);
    const showSecondary = visibleSecondaryAxis ?? hasNonBenchmarkSecondary;
    // An auto-scaled axis ends on nice ticks, so its extremes keep their line and label;
    // only an explicit domain that ends off the tick ladder hides an extreme.
    const primaryExtremes = extremeLabelVisibility(yDomain, yScaleType, resolvedYSplitNumber);
    return {
      backgroundColor: theme.background,
      useUTC: timeZone === 'utc',
      grid: linkedGrid
        ? { ...linkedGrid, containLabel: false, show: false, borderWidth: 0 }
        : {
            // containLabel keeps the tick labels inside, so every side is the card inset.
            top: preservePlotGeometry ? padding.top : QF_CHART_INSET,
            right: preservePlotGeometry ? padding.right : QF_CHART_INSET,
            bottom: preservePlotGeometry ? padding.bottom : QF_CHART_INSET,
            left: preservePlotGeometry ? padding.left : QF_CHART_INSET + nameBand,
            containLabel: !preservePlotGeometry,
            show: false,
            borderWidth: 0,
          },
      xAxis: {
        type: 'time',
        min: resolvedXDomain?.[0].getTime(),
        max: resolvedXDomain?.[1].getTime(),
        boundaryGap: [0, 0],
        axisLabel: {
          show: drawsTimeAxis,
          color: theme.axis,
          fontSize: theme.axisFontSize,
          formatter: (value: number, index: number) =>
            formatTimeTick(new Date(value), effectiveXDomain, index, timeZone),
          hideOverlap: true,
          // Overlap hiding measures the label box, which counts padding only when the box
          // has a (here invisible) background: neighbouring time labels then keep at least
          // TIME_LABEL_MIN_GAP between them instead of touching.
          padding: [0, TIME_LABEL_MIN_GAP / 2],
          backgroundColor: 'transparent',
        },
        axisLine: {
          show: drawsTimeAxis,
          lineStyle: { color: theme.frame, width: 1 },
          onZero: false,
        },
        // Horizontal gridlines carry the value reading; vertical ones only add noise.
        axisTick: { show: false },
        splitLine: { show: false },
        // A linked stack draws one crosshair over every pane, so the per-pane pointer is
        // invisible; it stays enabled because an axis with a hidden pointer never triggers
        // the axis tooltip. Once the stack owns the tooltip too, the pointer goes entirely.
        axisPointer: {
          show: drawsTooltip,
          type: linkedGrid ? 'none' : 'line',
          snap: false,
          animation: false,
          label: { show: false },
          lineStyle: { color: theme.crosshair, width: QF_CHART_RULE_WIDTH, type: CROSSHAIR_DASH },
        },
      },
      yAxis: [
        {
          type: yScaleType === 'log' ? 'log' : 'value',
          name: yAxisName,
          nameLocation: 'middle',
          nameGap: yAxisNameGap,
          nameTextStyle: { color: theme.axis, fontSize: theme.axisFontSize },
          min: yDomain?.[0],
          max: yDomain?.[1],
          inverse: yAxisInverse,
          scale: true,
          splitNumber: resolvedYSplitNumber,
          axisLabel: {
            show: showYAxisLabels,
            color: theme.axis,
            fontSize: theme.axisFontSize,
            formatter: resolvedYFormat,
            ...(linkedGrid ? { margin: PANE_LABEL_MARGIN } : {}),
            ...primaryExtremes,
          },
          // The gridlines already mark every tick, so the value axis draws no rule of its own.
          axisLine: { show: false, onZero: true },
          axisTick: { show: false },
          // A gridline at a padded extreme carries no label, so it goes with its label. A
          // linked pane above the time axis drops its bottom-edge gridline: the pane divider
          // is that rule, and both would draw a double line.
          splitLine: {
            show: true,
            showMinLine: primaryExtremes.showMinLabel !== false && !(dividesBelow && !yAxisInverse),
            showMaxLine: primaryExtremes.showMaxLabel !== false && !(dividesBelow && yAxisInverse),
            lineStyle: { color: theme.grid, opacity: theme.gridOpacity, type: 'solid', width: 1 },
          },
        },
        ...(hasNonBenchmarkSecondary
          ? [
              {
                type: 'value',
                name: ySecondaryAxisName,
                nameLocation: 'middle',
                nameGap: 50,
                nameTextStyle: { color: theme.axis, fontSize: theme.axisFontSize },
                min: ySecondaryDomain?.[0],
                max: ySecondaryDomain?.[1],
                inverse: ySecondaryAxisInverse,
                position: 'right',
                scale: true,
                show: showSecondary,
                axisLabel: {
                  show: showSecondary,
                  color: theme.axis,
                  fontSize: theme.axisFontSize,
                  formatter: resolvedYSecondaryFormat,
                  ...extremeLabelVisibility(ySecondaryDomain, 'linear'),
                },
                axisLine: { show: false },
                axisTick: { show: false },
                splitLine: { show: false },
              },
            ]
          : []),
        ...(hasNonBenchmarkTertiary
          ? [
              {
                type: 'value',
                name: yTertiaryAxisName,
                nameLocation: 'middle',
                nameGap: 50,
                nameTextStyle: { color: theme.axis, fontSize: theme.axisFontSize },
                min: yTertiaryDomain?.[0],
                max: yTertiaryDomain?.[1],
                position: 'right',
                offset: hasNonBenchmarkSecondary ? 72 : 0,
                scale: true,
                show: visibleTertiaryAxis ?? true,
                axisLabel: {
                  show: visibleTertiaryAxis ?? true,
                  color: theme.axis,
                  fontSize: theme.axisFontSize,
                  formatter: resolvedYTertiaryFormat,
                  ...extremeLabelVisibility(yTertiaryDomain, 'linear'),
                },
                axisLine: { show: false },
                axisTick: { show: false },
                splitLine: { show: false },
              },
            ]
          : []),
        ...(hasBenchmark
          ? [
              {
                type: (sharesScale ? yScaleType : benchmarkScaleType) === 'log' ? 'log' : 'value',
                min: (sharesScale ? yDomain : benchmarkDomain)?.[0],
                max: (sharesScale ? yDomain : benchmarkDomain)?.[1],
                scale: true,
                show: false,
                axisLabel: { show: false },
                axisLine: { show: false },
                axisTick: { show: false },
                splitLine: { show: false },
              },
            ]
          : []),
      ],
      tooltip: drawsTooltip
        ? {
            ...qfEChartsTooltip(theme),
            trigger: 'axis',
            axisPointer: {
              type: linkedGrid ? 'none' : 'line',
              axis: 'x',
              snap: false,
              animation: false,
              label: { show: false },
              lineStyle: {
                color: theme.crosshair,
                width: QF_CHART_RULE_WIDTH,
                type: CROSSHAIR_DASH,
              },
            },
            formatter: tooltipHtml
              ? (params: unknown) => {
                  const date = tooltipDate(params);
                  return date ? tooltipHtml(date) : '';
                }
              : // The qf rows, never ECharts' default `{marker}` list of circles.
                seriesTooltipHtml,
          }
        : { show: false },
      aria: { enabled: true, decal: { show: false } },
    };
  }, [
    benchmarkDomain,
    benchmarkScale,
    benchmarkScaleType,
    sharesScale,
    dividesBelow,
    drawsTimeAxis,
    drawsTooltip,
    effectiveXDomain,
    linkedGrid,
    model.plotted,
    nameBand,
    padding,
    preservePlotGeometry,
    resolvedXDomain,
    resolvedYSplitNumber,
    showYAxisLabels,
    theme,
    tooltipHtml,
    timeZone,
    seriesTooltipHtml,
    visibleSecondaryAxis,
    visibleTertiaryAxis,
    yAxisName,
    yAxisNameGap,
    yDomain,
    resolvedYFormat,
    yAxisInverse,
    yScaleType,
    ySecondaryDomain,
    ySecondaryAxisName,
    resolvedYSecondaryFormat,
    ySecondaryAxisInverse,
    yTertiaryAxisName,
    yTertiaryDomain,
    resolvedYTertiaryFormat,
  ]);
  // Only a hovered legend row (emphasizedSeries) focuses a series; the plot never does.
  const seriesIds = useMemo(() => baseSeries.map((entry) => entry.id), [baseSeries]);
  const focusTarget =
    emphasizedSeries != null && seriesIds.includes(emphasizedSeries) ? emphasizedSeries : null;
  const drawnPoints = useMemo(
    () => baseSeries.reduce((total, entry) => total + entry.data.length, 0),
    [baseSeries],
  );
  const focusLevels = useFocusFade(seriesIds, focusTarget, drawnPoints <= FOCUS_FADE_MAX_POINTS);
  // Series swaps and legend toggles repaint instantly: the stroke never draws in from
  // the left. Only focus changes ease, as an opacity-only patch that resends no data.
  const option = useMemo<QfChartOption>(
    () => ({ ...baseOption, animation: false, series: baseSeries }),
    [baseOption, baseSeries],
  );
  const seriesPatch = useMemo<QfChartOption[] | undefined>(() => {
    if (focusLevels.size === 0) return undefined;
    return baseSeries.map((entry) => {
      const level = focusLevels.get(entry.id) ?? 1;
      const lineStyle = { opacity: entry.lineStyle.opacity * level };
      const areaStyle = entry.areaStyle ? { opacity: entry.areaStyle.opacity * level } : undefined;
      return {
        id: entry.id,
        lineStyle,
        itemStyle: { opacity: entry.itemStyle.opacity * level },
        ...(areaStyle ? { areaStyle } : {}),
        emphasis: { lineStyle, ...(areaStyle ? { areaStyle } : {}) },
      };
    });
  }, [baseSeries, focusLevels]);

  return (
    <QfChart
      option={option}
      seriesPatch={seriesPatch}
      height={height}
      ariaLabel={ariaLabel}
      className={className}
    />
  );
}
