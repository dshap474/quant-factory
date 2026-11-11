/**
 * Domain-aware time-axis labels and tooltip dates shared by qf-charts renderers.
 *
 * Ticks use landmarks: a year start shows the year, a month start shows the month,
 * any other day shows `15 Jul`, spans under two minutes show `14:00:05`,
 * and spans under two days show 24-hour `14:00` with
 * `15 Jul` at midnight (local by default, UTC when requested). On spans of 90 days or more the first tick carries the
 * year (`Jul 2024`). Month and weekday names come from the one date grammar in
 * `lib/time-format.ts`.
 *
 * USAGE:
 *   formatTimeTick(new Date(timestamp), [start, end], tickIndex);
 *   formatDateTick(new Date(timestamp), [start, end]); // alias without the index
 *   formatTooltipDate(new Date(2021, 2, 5)); // "Fri 5 Mar 2021"
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { MONTH_LABELS, WEEKDAY_LABELS } from '../../lib/time-format';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const DAY_MS = 24 * 60 * 60 * 1000;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function isMidnight(value: Date, utc: boolean): boolean {
  return (
    (utc ? value.getUTCHours() : value.getHours()) === 0 &&
    (utc ? value.getUTCMinutes() : value.getMinutes()) === 0 &&
    (utc ? value.getUTCSeconds() : value.getSeconds()) === 0 &&
    (utc ? value.getUTCMilliseconds() : value.getMilliseconds()) === 0
  );
}

function isMonthStart(value: Date, utc: boolean): boolean {
  return (utc ? value.getUTCDate() : value.getDate()) === 1 && isMidnight(value, utc);
}

function isYearStart(value: Date, utc: boolean): boolean {
  return (utc ? value.getUTCMonth() : value.getMonth()) === 0 && isMonthStart(value, utc);
}

const pad2 = (value: number) => `${value}`.padStart(2, '0');

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

/**
 * Axis tick label. `index` is the tick's position on the axis; on spans of 90 days or
 * more, index 0 carries the year so the reader can place every later landmark.
 */
export function formatTimeTick(
  value: Date,
  domain: readonly [Date, Date] | null,
  index?: number,
  timeZone: 'local' | 'utc' = 'local',
): string {
  const timestamp = value.getTime();
  if (!Number.isFinite(timestamp)) return '';

  const start = domain?.[0].getTime() ?? Number.NaN;
  const end = domain?.[1].getTime() ?? Number.NaN;
  const span =
    Number.isFinite(start) && Number.isFinite(end) && start !== end ? Math.abs(end - start) : null;
  const utc = timeZone === 'utc';
  const day = `${utc ? value.getUTCDate() : value.getDate()}`;
  const month = MONTH_LABELS[utc ? value.getUTCMonth() : value.getMonth()] ?? '';
  const year = `${utc ? value.getUTCFullYear() : value.getFullYear()}`;
  const hour = utc ? value.getUTCHours() : value.getHours();
  const minute = utc ? value.getUTCMinutes() : value.getMinutes();

  if (span !== null && span < 2 * DAY_MS) {
    if (isMidnight(value, utc)) return `${day} ${month}`;
    if (span < 120_000)
      return `${pad2(hour)}:${pad2(minute)}:${pad2(utc ? value.getUTCSeconds() : value.getSeconds())}`;
    return `${pad2(hour)}:${pad2(minute)}`;
  }

  if (isYearStart(value, utc)) return year;
  const anchorsYear = index === 0 && (span === null || span >= 90 * DAY_MS);
  const label = isMonthStart(value, utc) ? month : `${day} ${month}`;
  return anchorsYear ? `${label} ${year}` : label;
}

/** Public alias kept for existing callers; it has no tick index. */
export function formatDateTick(value: Date, domain: readonly [Date, Date] | null): string {
  return formatTimeTick(value, domain);
}

/**
 * Tooltip header date. The day-month-year order matches the axis ticks, so a reader
 * never has to translate between `3/26/2021` in the tooltip and `26 Mar` on the axis;
 * the clock time appears only for observations that are not at local midnight.
 */
export function formatTooltipDate(value: Date, timeZone: 'local' | 'utc' = 'local'): string {
  const timestamp = value.getTime();
  if (!Number.isFinite(timestamp)) return '';
  const utc = timeZone === 'utc';
  const month = MONTH_LABELS[utc ? value.getUTCMonth() : value.getMonth()] ?? '';
  const weekday = WEEKDAY_LABELS[utc ? value.getUTCDay() : value.getDay()] ?? '';
  const date = `${weekday} ${utc ? value.getUTCDate() : value.getDate()} ${month} ${utc ? value.getUTCFullYear() : value.getFullYear()}`;
  const suffix = utc ? ' UTC' : '';
  if (isMidnight(value, utc)) return date + suffix;
  return `${date} ${pad2(utc ? value.getUTCHours() : value.getHours())}:${pad2(utc ? value.getUTCMinutes() : value.getMinutes())}${suffix}`;
}
