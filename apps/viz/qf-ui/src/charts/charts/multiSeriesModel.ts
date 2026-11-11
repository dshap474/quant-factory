/**
 * Package-owned multi-series chart model, formatting, downsampling, and lookup.
 *
 * USAGE:
 *   import { formatYAxis, lttb, findNearestPoint } from './multiSeriesModel';
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { extentOf } from '../../lib/extent';
import { parseLocalDay } from '../../lib/time-format';
import { chartPaletteColor } from '../theme/chartColor';
import type { QfInterpolation } from './interpolation';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type MultiSeriesAxis = 'left' | 'right' | 'tertiary';
export type MultiSeriesValueFormat =
  | 'basis-points'
  | 'number'
  | 'money'
  | 'money-exact'
  | 'money-millions'
  | 'percent'
  | 'percent-delta'
  | 'percent-points'
  | 'percentage-points'
  | 'rank'
  | 'rank-delta';

export interface MultiSeriesPoint {
  date: Date;
  value: number;
  /**
   * Optional segment flag for discontinuous areas (e.g. regime membership).
   * When set on series with `defined`, only points where active !== false paint.
   */
  active?: boolean;
}

export interface MultiSeriesNullablePoint extends Omit<MultiSeriesPoint, 'value'> {
  value: number | null;
}

export interface MultiSeriesSourcePoint {
  x: string | Date;
  y: number;
}

export interface MultiSeriesNullableSourcePoint extends Omit<MultiSeriesSourcePoint, 'y'> {
  y: number | null;
}

export interface MultiSeriesSourceSeries {
  metric: string;
  axis: MultiSeriesAxis;
  label: string;
  valueFormat?: MultiSeriesValueFormat;
  isBenchmark?: boolean;
  /** Plots on the series' own axis but stays out of the legend (a main-axis benchmark overlay). */
  hideFromLegend?: boolean;
  /** How this line joins its points; overrides the chart's `interpolation`. */
  interpolation?: QfInterpolation;
  points: readonly MultiSeriesSourcePoint[];
  /** Earlier observations used to initialize transforms but never plotted directly. */
  transformHistory?: readonly MultiSeriesSourcePoint[];
}

export interface MultiSeriesNullableSourceSeries
  extends Omit<MultiSeriesSourceSeries, 'points' | 'transformHistory'> {
  points: readonly MultiSeriesNullableSourcePoint[];
  transformHistory?: readonly MultiSeriesNullableSourcePoint[];
}

export interface MultiSeriesPlotSeries {
  metric: string;
  axis: MultiSeriesAxis;
  label: string;
  valueFormat?: MultiSeriesValueFormat;
  color: string;
  isBenchmark?: boolean;
  hideFromLegend?: boolean;
  interpolation?: QfInterpolation;
  opacity?: number;
  points: MultiSeriesNullablePoint[];
  transformHistory?: MultiSeriesNullablePoint[];
}

export interface MultiSeriesOverlay {
  id: string;
  label: string;
  points: MultiSeriesPoint[];
}

// --------------------------------------------------------------------------- #
// Normalization and domains
// --------------------------------------------------------------------------- #

/**
 * Default series colours when the host passes no `metricColors`: the first plotted
 * series takes `primaryColor` (series 1, the brand gold) and each later one the next
 * palette slot, so an uncoloured chart never draws every line in the primary colour.
 * Benchmarks are skipped; they always use the semantic benchmark tone.
 */
export function paletteMetricColors(
  source: readonly Pick<MultiSeriesSourceSeries, 'metric' | 'isBenchmark'>[],
  primaryColor: string,
): Readonly<Record<string, string>> {
  const colors: Record<string, string> = {};
  let index = 0;
  for (const item of source) {
    if (item.isBenchmark || item.metric in colors) continue;
    colors[item.metric] = index === 0 ? primaryColor : chartPaletteColor(index);
    index += 1;
  }
  return colors;
}

export function parseMultiSeries(
  source: readonly (MultiSeriesSourceSeries | MultiSeriesNullableSourceSeries)[],
  colors: Readonly<Record<string, string>>,
  fallbackColor: string,
): MultiSeriesPlotSeries[] {
  const parsed: MultiSeriesPlotSeries[] = [];
  for (const item of source) {
    const points = parseSourcePoints(item.points);
    if (points.length === 0) continue;
    const transformHistory = parseSourcePoints(item.transformHistory ?? []);
    parsed.push({
      metric: item.metric,
      axis: item.axis,
      label: item.label,
      ...(item.valueFormat === undefined ? {} : { valueFormat: item.valueFormat }),
      color: colors[item.metric] ?? fallbackColor,
      ...(item.isBenchmark === undefined ? {} : { isBenchmark: item.isBenchmark }),
      ...(item.hideFromLegend === undefined ? {} : { hideFromLegend: item.hideFromLegend }),
      ...(item.interpolation === undefined ? {} : { interpolation: item.interpolation }),
      points,
      ...(transformHistory.length === 0 ? {} : { transformHistory }),
    });
  }
  return parsed;
}

export function parseSourcePoints(
  source: readonly MultiSeriesNullableSourcePoint[],
): MultiSeriesNullablePoint[] {
  const points: MultiSeriesNullablePoint[] = [];
  for (const sourcePoint of source) {
    const value = sourcePoint.y === null ? null : Number(sourcePoint.y);
    const point = { date: parseSourceDate(sourcePoint.x), value };
    if (
      !Number.isNaN(point.date.getTime()) &&
      (point.value === null || Number.isFinite(point.value))
    )
      points.push(point);
  }
  return points.sort((left, right) => left.date.getTime() - right.date.getTime());
}

function parseSourceDate(value: string | Date): Date {
  if (value instanceof Date || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return new Date(value);
  return parseLocalDay(value);
}

export function collectDomainPoints(series: readonly MultiSeriesPlotSeries[]): MultiSeriesPoint[] {
  const seen = new Set<number>();
  const points: MultiSeriesPoint[] = [];
  for (const item of series) {
    for (const point of item.points) {
      const time = point.date.getTime();
      if (seen.has(time)) continue;
      seen.add(time);
      points.push({ date: point.date, value: 0 });
    }
  }
  return points.sort((left, right) => left.date.getTime() - right.date.getTime());
}

/** `[min, max]` of the finite-or-infinite values (NaN skipped); `[Infinity, -Infinity]` when none. */
export function extent(values: readonly number[]): [number, number] {
  const range = extentOf(values);
  return range ? [range.min, range.max] : [Infinity, -Infinity];
}

export function paddedDomain(values: readonly number[]): [number, number] {
  if (values.length === 0) return [0, 1];
  const [min, max] = extent(values);
  if (min === max) {
    const padding = Math.abs(min || 1) * 0.08;
    return [min - padding, max + padding];
  }
  const padding = (max - min) * 0.08;
  return [min - padding, max + padding];
}

export function axisDomain(
  series: readonly MultiSeriesPlotSeries[],
  axis: MultiSeriesAxis,
  format: MultiSeriesValueFormat = 'number',
): [number, number] {
  if (format === 'percent') return [0, 1];

  const values: number[] = [];
  for (const item of series) {
    if (item.isBenchmark || item.axis !== axis) continue;
    for (const point of item.points) {
      if (point.value !== null) values.push(point.value);
    }
  }
  if (format === 'rank') {
    if (values.length === 0) return [1, 2];
    return [1, Math.max(2, Math.ceil(extent(values)[1]))];
  }
  if (format === 'rank-delta') {
    if (values.length === 0) return [-1, 1];
    const [min, max] = extent(values);
    const magnitude = Math.max(1, Math.ceil(Math.max(Math.abs(min), Math.abs(max))));
    return [-magnitude, magnitude];
  }
  return paddedDomain(values);
}

/** Value axis a hover dot is measured against: the plotted domain, its scale, and direction. */
export interface MultiSeriesValueAxis {
  domain: readonly [number, number];
  scale: 'linear' | 'log';
  inverse: boolean;
}

/**
 * Vertical pixel of `value` on a value axis spanning `innerHeight` below `marginTop`,
 * or null when the value falls outside the axis or cannot be placed on it.
 */
export function valueToPlotY(
  value: number,
  axis: MultiSeriesValueAxis,
  marginTop: number,
  innerHeight: number,
): number | null {
  const [min, max] = axis.domain;
  const project = axis.scale === 'log' ? Math.log10 : (input: number) => input;
  if (axis.scale === 'log' && !(value > 0 && min > 0 && max > 0)) return null;
  const span = project(max) - project(min);
  const ratio = (project(value) - project(min)) / span;
  if (!Number.isFinite(ratio) || ratio < -1e-9 || ratio > 1 + 1e-9) return null;
  return marginTop + (axis.inverse ? ratio : 1 - ratio) * innerHeight;
}

/** Multiplicatively padded positive domain for a log-scaled axis; non-positive values are dropped. */
export function logAxisDomain(
  series: readonly MultiSeriesPlotSeries[],
  axis: MultiSeriesAxis,
): [number, number] {
  const values: number[] = [];
  for (const item of series) {
    if (item.isBenchmark || item.axis !== axis) continue;
    for (const point of item.points) {
      if (point.value !== null && point.value > 0) values.push(point.value);
    }
  }
  if (values.length === 0) return [1, 10];
  const [min, max] = extent(values);
  return [min / 1.05, max * 1.05];
}

export function dateDomain(
  points: readonly MultiSeriesPoint[],
  selected?: readonly [Date, Date],
): [Date, Date] {
  if (selected) return [selected[0], selected[1]];
  if (points.length === 0) {
    const now = new Date();
    return [now, new Date(now.getTime() + DAY_MS)];
  }
  const [min, max] = extent(points.map((point) => point.date.getTime()));
  if (min === max) return [new Date(min - DAY_MS), new Date(max + DAY_MS)];
  return [new Date(min), new Date(max)];
}

const DAY_MS = 24 * 60 * 60 * 1000;

export function formatYAxis(value: number, format: MultiSeriesValueFormat = 'number'): string {
  if (format === 'money-exact')
    return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  if (format === 'rank' || format === 'rank-delta') return formatRank(value);
  if (format === 'basis-points') return `${formatYAxis(value, 'number')} bp`;

  if (
    format === 'percent' ||
    format === 'percent-delta' ||
    format === 'percent-points' ||
    format === 'percentage-points'
  ) {
    const percentage = format === 'percent-points' ? value : value * 100;
    const displayed = format === 'percentage-points' ? value : percentage;
    const absolutePercentage = Math.abs(displayed);
    const formatted =
      absolutePercentage >= 100
        ? displayed.toFixed(0)
        : absolutePercentage >= 1
          ? displayed.toFixed(2)
          : displayed.toPrecision(3);
    return `${trimZeros(formatted)}${format === 'percentage-points' ? ' pp' : '%'}`;
  }

  const normalizedValue = format === 'money-millions' ? value * 1_000_000 : value;
  const absolute = Math.abs(normalizedValue);
  const isMoney = format === 'money' || format === 'money-millions';
  const displayed = isMoney ? absolute : normalizedValue;
  const prefix = isMoney ? `${normalizedValue < 0 ? '-' : ''}$` : '';
  if (absolute >= 1_000_000_000)
    return `${prefix}${trimZeros((displayed / 1_000_000_000).toFixed(2))}B`;
  if (absolute >= 1_000_000) return `${prefix}${trimZeros((displayed / 1_000_000).toFixed(2))}M`;
  if (absolute >= 1_000) return `${prefix}${trimZeros((displayed / 1_000).toFixed(1))}K`;
  if (absolute >= 1) return `${prefix}${trimZeros(displayed.toFixed(2))}`;
  return `${prefix}${trimZeros(displayed.toPrecision(3))}`;
}

/**
 * Drops trailing fractional zeros ("1.50K" -> "1.5K", "100.00" -> "100"). Axis ticks
 * sit on round values, so padded zeros only widen the gutter and make `100.00` and
 * `1.0K` read as different precisions on one axis; tooltips keep their fixed digits.
 */
function trimZeros(text: string): string {
  if (!text.includes('.')) return text;
  return text.replace(/(\.\d*?)0+(?=$|e)/, '$1').replace(/\.(?=$|e)/, '');
}

export function formatTooltipValue(
  value: number,
  format: MultiSeriesValueFormat = 'number',
): string {
  if (format === 'money-exact') return formatYAxis(value, format);
  if (format === 'rank' || format === 'rank-delta') return formatRank(value);
  if (format === 'basis-points') return `${formatTooltipValue(value, 'number')} bp`;

  if (
    format === 'percent' ||
    format === 'percent-delta' ||
    format === 'percent-points' ||
    format === 'percentage-points'
  ) {
    const percentage = format === 'percent-points' ? value : value * 100;
    const displayed = format === 'percentage-points' ? value : percentage;
    const absolutePercentage = Math.abs(displayed);
    const formatted =
      absolutePercentage >= 1000
        ? displayed.toLocaleString(undefined, { maximumFractionDigits: 2 })
        : absolutePercentage >= 1
          ? displayed.toFixed(4)
          : displayed.toPrecision(4);
    return `${formatted}${format === 'percentage-points' ? ' pp' : '%'}`;
  }

  const normalizedValue = format === 'money-millions' ? value * 1_000_000 : value;
  const absolute = Math.abs(normalizedValue);
  const isMoney = format === 'money' || format === 'money-millions';
  const displayed = isMoney ? absolute : normalizedValue;
  // Six significant digits keep neighbouring tooltip rows at one precision: 1,063.37
  // above 1,000 and 383.455 below it, instead of 383.4545 beside 1,063.37.
  const formatted =
    absolute >= 1000
      ? displayed.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : absolute >= 1
        ? displayed.toLocaleString(undefined, { maximumSignificantDigits: 6 })
        : displayed.toPrecision(4);
  return isMoney ? `${normalizedValue < 0 ? '-' : ''}$${formatted}` : formatted;
}

function formatRank(value: number): string {
  return value.toLocaleString(undefined, {
    maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
  });
}

export { formatDateTick, formatTimeTick, formatTooltipDate } from './timeAxisFormat';

export function upperBound<T extends { date: Date }>(points: readonly T[], target: number): number {
  let lo = 0;
  let hi = points.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    const point = points[mid];
    if (!point) break;
    if (point.date.getTime() <= target) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * Largest-Triangle-Three-Buckets downsampling for a time-ordered line series. Reduces a dense
 * series to `threshold` points while preserving visual shape (peaks/valleys/inflections), so a
 * ~1900-point line renders as ~1 point per pixel with no perceptible loss. Returns the input
 * unchanged when it already has `threshold` points or fewer (so sparse charts are untouched).
 * Points are assumed sorted ascending by date (the callers order server-side by time).
 */
export function lttb(points: MultiSeriesPoint[], threshold: number): MultiSeriesPoint[];
export function lttb(
  points: MultiSeriesNullablePoint[],
  threshold: number,
): MultiSeriesNullablePoint[];
export function lttb(
  points: MultiSeriesNullablePoint[],
  threshold: number,
): MultiSeriesNullablePoint[] {
  const n = points.length;
  if (threshold >= n || threshold < 3) return points;
  if (points.some((point) => point.value === null)) return points;
  const first = points[0];
  const last = points[n - 1];
  if (!first || !last) return points;

  const sampled: MultiSeriesNullablePoint[] = [first];
  const bucketSize = (n - 2) / (threshold - 2);
  let a = 0; // index of the last selected point (anchor for the triangle)

  for (let i = 0; i < threshold - 2; i++) {
    // Average of the NEXT bucket (the third triangle vertex).
    const avgStart = Math.floor((i + 1) * bucketSize) + 1;
    let avgEnd = Math.floor((i + 2) * bucketSize) + 1;
    avgEnd = avgEnd < n ? avgEnd : n;
    const avgLen = avgEnd - avgStart || 1;
    let avgX = 0;
    let avgY = 0;
    for (let j = avgStart; j < avgEnd; j++) {
      const point = points[j];
      if (!point || point.value === null) continue;
      avgX += point.date.getTime();
      avgY += point.value;
    }
    avgX /= avgLen;
    avgY /= avgLen;

    // Pick the point in THIS bucket that forms the largest-area triangle with a → avg.
    const rangeStart = Math.floor(i * bucketSize) + 1;
    const rangeEnd = Math.floor((i + 1) * bucketSize) + 1;
    const anchor = points[a];
    if (!anchor) continue;
    const aX = anchor.date.getTime();
    const aY = anchor.value;
    if (aY === null) return points;
    let maxArea = -1;
    let nextA = rangeStart;
    for (let j = rangeStart; j < rangeEnd; j++) {
      const point = points[j];
      if (!point || point.value === null) continue;
      const area =
        Math.abs((aX - avgX) * (point.value - aY) - (aX - point.date.getTime()) * (avgY - aY)) *
        0.5;
      if (area > maxArea) {
        maxArea = area;
        nextA = j;
      }
    }
    const selected = points[nextA];
    if (!selected) continue;
    sampled.push(selected);
    a = nextA;
  }

  sampled.push(last);
  return sampled;
}

export function findNearestPoint(
  points: readonly MultiSeriesPoint[],
  targetDate: Date,
  maxDistanceMs?: number,
): MultiSeriesPoint | null;
export function findNearestPoint(
  points: readonly MultiSeriesNullablePoint[],
  targetDate: Date,
  maxDistanceMs?: number,
): MultiSeriesNullablePoint | null;
export function findNearestPoint(
  points: readonly MultiSeriesNullablePoint[],
  targetDate: Date,
  maxDistanceMs = Number.POSITIVE_INFINITY,
): MultiSeriesNullablePoint | null {
  if (points.length === 0) return null;
  const target = targetDate.getTime();
  const index = upperBound(points, target);
  const prev = points[index - 1];
  const next = points[index];
  const nearest = !prev
    ? (next ?? null)
    : !next
      ? prev
      : Math.abs(next.date.getTime() - target) < Math.abs(target - prev.date.getTime())
        ? next
        : prev;
  if (!nearest || Math.abs(nearest.date.getTime() - target) > maxDistanceMs) return null;
  return nearest;
}
