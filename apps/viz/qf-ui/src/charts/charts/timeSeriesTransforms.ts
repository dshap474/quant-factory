/**
 * Package-owned trailing Z-score and EMA transforms for time-series charts.
 *
 * USAGE:
 *   const transformed = applyTimeSeriesTransforms(series, { zScore: 30, ema: 90 });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type {
  MultiSeriesNullablePoint,
  MultiSeriesPlotSeries,
  MultiSeriesPoint,
  MultiSeriesValueFormat,
} from './multiSeriesModel';

// --------------------------------------------------------------------------- #
// Public contract
// --------------------------------------------------------------------------- #

export const CHART_Z_SCORE_WINDOWS = [30, 90, 180, 365] as const;
export const CHART_EMA_WINDOWS = [30, 90] as const;

export type ChartTransformWindow = (typeof CHART_Z_SCORE_WINDOWS)[number];

export interface ChartTransformControls {
  readonly zScore?: boolean | readonly ChartTransformWindow[];
  readonly ema?: boolean | readonly ChartTransformWindow[];
}

export interface ChartTransformState {
  readonly zScore: ChartTransformWindow | null;
  readonly ema: ChartTransformWindow | null;
}

export const DEFAULT_CHART_TRANSFORM_STATE: ChartTransformState = {
  zScore: null,
  ema: null,
};

export function resolveChartTransformWindows(
  control: boolean | readonly ChartTransformWindow[] | undefined,
  defaults: readonly ChartTransformWindow[],
): readonly ChartTransformWindow[] {
  if (Array.isArray(control)) return control;
  return control ? defaults : [];
}

// --------------------------------------------------------------------------- #
// Point transforms
// --------------------------------------------------------------------------- #

const DAY_MS = 24 * 60 * 60 * 1000;

interface RollingMoments {
  count: number;
  mean: number;
  squaredDeviation: number;
}

function addRollingValue(moments: RollingMoments, value: number): void {
  moments.count += 1;
  const delta = value - moments.mean;
  moments.mean += delta / moments.count;
  moments.squaredDeviation += delta * (value - moments.mean);
}

function removeRollingValue(moments: RollingMoments, value: number): void {
  if (moments.count <= 1) {
    moments.count = 0;
    moments.mean = 0;
    moments.squaredDeviation = 0;
    return;
  }
  const nextCount = moments.count - 1;
  const nextMean = (moments.count * moments.mean - value) / nextCount;
  moments.squaredDeviation = Math.max(
    0,
    moments.squaredDeviation - (value - moments.mean) * (value - nextMean),
  );
  moments.count = nextCount;
  moments.mean = nextMean;
}

export function trailingZScore(
  points: readonly MultiSeriesNullablePoint[],
  windowDays: number,
): MultiSeriesPoint[] {
  const numericPoints = points.filter(
    (point): point is MultiSeriesPoint & { value: number } => point.value !== null,
  );
  const first = numericPoints[0];
  if (!first || !Number.isInteger(windowDays) || windowDays < 1) return [];
  const windowMs = windowDays * DAY_MS;
  const moments: RollingMoments = { count: 0, mean: 0, squaredDeviation: 0 };
  const transformed: MultiSeriesPoint[] = [];
  let startIndex = 0;
  for (const point of numericPoints) {
    addRollingValue(moments, point.value);
    const cutoff = point.date.getTime() - windowMs;
    while (startIndex < numericPoints.length) {
      const oldest = numericPoints[startIndex];
      if (!oldest || oldest.date.getTime() > cutoff) break;
      removeRollingValue(moments, oldest.value);
      startIndex += 1;
    }
    if (point.date.getTime() - first.date.getTime() < windowMs || moments.count < 2) continue;
    const deviation = Math.sqrt(moments.squaredDeviation / moments.count);
    const value = deviation === 0 ? 0 : (point.value - moments.mean) / deviation;
    transformed.push({ ...point, value });
  }
  return transformed;
}

export function exponentialMovingAverage(
  points: readonly MultiSeriesNullablePoint[],
  windowDays: number,
  displayFrom?: Date,
): MultiSeriesPoint[] {
  const numericPoints = points.filter(
    (point): point is MultiSeriesPoint & { value: number } => point.value !== null,
  );
  const first = numericPoints[0];
  if (!first || !Number.isInteger(windowDays) || windowDays < 1) return [];
  const windowMs = windowDays * DAY_MS;
  const fullWindowSeedIndex = numericPoints.findIndex(
    (point) => point.date.getTime() - first.date.getTime() >= windowMs,
  );
  const displayTime = displayFrom?.getTime();
  const displayIndex =
    displayTime === undefined
      ? -1
      : numericPoints.findIndex((point) => point.date.getTime() >= displayTime);
  const seedIndex =
    displayIndex >= 0 && (fullWindowSeedIndex < 0 || displayIndex < fullWindowSeedIndex)
      ? displayIndex
      : fullWindowSeedIndex;
  const seed = numericPoints[seedIndex];
  if (!seed) return [];

  const seedCutoff = seed.date.getTime() - windowMs;
  const seedWindow = numericPoints
    .slice(0, seedIndex + 1)
    .filter((point) => point.date.getTime() > seedCutoff);
  let previous = seedWindow.reduce((total, point) => total + point.value, 0) / seedWindow.length;
  let previousTime = seed.date.getTime();
  const dailyRetention = 1 - 2 / (windowDays + 1);
  const transformed: MultiSeriesPoint[] = [{ ...seed, value: previous }];

  for (const point of numericPoints.slice(seedIndex + 1)) {
    const elapsedDays = Math.max((point.date.getTime() - previousTime) / DAY_MS, 0);
    const retention = dailyRetention ** elapsedDays;
    previous = (1 - retention) * point.value + retention * previous;
    previousTime = point.date.getTime();
    transformed.push({ ...point, value: previous });
  }
  return displayTime === undefined
    ? transformed
    : transformed.filter((point) => point.date.getTime() >= displayTime);
}

// --------------------------------------------------------------------------- #
// Series transforms
// --------------------------------------------------------------------------- #

export function applyTimeSeriesTransforms(
  series: readonly MultiSeriesPlotSeries[],
  state: ChartTransformState,
): readonly MultiSeriesPlotSeries[] {
  if (state.zScore == null && state.ema == null) return series;
  return series.map((item) => {
    if (item.isBenchmark) return item;
    const transformHistory = mergeTransformHistory(item.transformHistory, item.points);
    const displayFrom = item.transformHistory === undefined ? undefined : item.points[0]?.date;
    const normalized =
      state.zScore == null ? transformHistory : trailingZScore(transformHistory, state.zScore);
    const transformed =
      state.ema == null ? normalized : exponentialMovingAverage(normalized, state.ema, displayFrom);
    const points =
      displayFrom === undefined
        ? transformed
        : transformed.filter((point) => point.date.getTime() >= displayFrom.getTime());
    return { ...item, points };
  });
}

function mergeTransformHistory(
  history: readonly MultiSeriesNullablePoint[] | undefined,
  points: readonly MultiSeriesNullablePoint[],
): MultiSeriesNullablePoint[] {
  if (history === undefined) return [...points];
  const byTime = new Map<number, MultiSeriesNullablePoint>();
  for (const point of history) byTime.set(point.date.getTime(), point);
  for (const point of points) byTime.set(point.date.getTime(), point);
  return [...byTime.values()].sort((left, right) => left.date.getTime() - right.date.getTime());
}

export function transformedValueFormat(
  valueFormat: MultiSeriesValueFormat,
  state: ChartTransformState,
): MultiSeriesValueFormat {
  return state.zScore == null ? valueFormat : 'number';
}
