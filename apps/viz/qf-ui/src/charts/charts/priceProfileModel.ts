/** Pure coordinate and gap helpers for price/profile compositions.
 * USAGE: priceProfileExtent(model); breakLineGaps(points, 60_000).
 */
// --------------------------------------------------------------------------- #
// Imports and transformations
// --------------------------------------------------------------------------- #
import type { PriceProfileModel, PriceProfilePoint } from './priceProfileTypes';

/** Insert a null one `maxGap` after any point whose successor is further than `maxGap` away. */
export function breakLineGaps(
  points: readonly PriceProfilePoint[],
  maxGap: number | undefined,
): PriceProfilePoint[] {
  if (maxGap == null || !(maxGap > 0)) return [...points];
  const result: PriceProfilePoint[] = [];
  for (const point of points) {
    const previous = result.at(-1);
    if (previous && point[0] - previous[0] > maxGap) result.push([previous[0] + maxGap, null]);
    result.push(point);
  }
  return result;
}

/** One price domain for both panels, padded by 5% of its range (1 when flat). */
export function priceProfileExtent(model: PriceProfileModel): [number, number] {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  const [from, to] = clampWindow(model.window, model.xDomain);
  const inWindow = (time: number) => time >= from && time <= to;
  const add = (value: number | null | undefined) => {
    if (value == null || !Number.isFinite(value)) return;
    min = Math.min(min, value);
    max = Math.max(max, value);
  };
  for (const [time, value] of model.price.points) if (inWindow(time)) add(value);
  for (const bar of model.candles ?? []) {
    if (!inWindow(bar.availableTime)) continue;
    add(bar.high);
    add(bar.low);
  }
  for (const level of model.levels ?? [])
    for (const [time, value] of level.points) if (inWindow(time)) add(value);
  for (const segment of model.segments ?? [])
    if (segment.to >= from && segment.from <= to) add(segment.value);
  for (const marker of model.markers ?? []) if (inWindow(marker.time)) add(marker.value);
  for (const fill of model.fills?.points ?? []) if (inWindow(fill.time)) add(fill.price);
  for (const profile of model.profiles ?? []) {
    for (const [price] of profile.rows) add(price);
    add(profile.band?.[0]);
    add(profile.band?.[1]);
  }
  if (!Number.isFinite(min)) return [0, 1];
  const pad = max > min ? (max - min) * 0.05 : 1;
  return [min - pad, max + pad];
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** `HH:MM`, or `YYYY-MM-DD HH:MM` with `withDate`, in the chart's time zone. */
export function formatPriceProfileTime(
  time: number,
  timeZone: 'local' | 'utc',
  withDate = false,
): string {
  const date = new Date(time);
  if (Number.isNaN(date.getTime())) return '';
  const utc = timeZone === 'utc';
  const clock = `${pad2(utc ? date.getUTCHours() : date.getHours())}:${pad2(
    utc ? date.getUTCMinutes() : date.getMinutes(),
  )}`;
  if (!withDate) return clock;
  const day = `${utc ? date.getUTCFullYear() : date.getFullYear()}-${pad2(
    (utc ? date.getUTCMonth() : date.getMonth()) + 1,
  )}-${pad2(utc ? date.getUTCDate() : date.getDate())}`;
  return `${day} ${clock}${utc ? ' UTC' : ''}`;
}

export function clampWindow(
  window: readonly [number, number] | undefined,
  domain: readonly [number, number],
): [number, number] {
  if (!window) return [domain[0], domain[1]];
  return [Math.max(domain[0], window[0]), Math.min(domain[1], window[1])];
}
