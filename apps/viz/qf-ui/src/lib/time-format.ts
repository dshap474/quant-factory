/**
 * The one date grammar: day-month-year with short English month names
 * (`26 Mar 2021 14:05`), the order chart axes already render. Time zone is chosen
 * per surface (tables UTC, chart tooltips local), so no displayed instant moves.
 * Also the compact labels around it: ISO calendar days, short local date-times,
 * and elapsed durations.
 *
 * USAGE:
 *   import { formatTimestamp } from '@quant-factory/qf-ui';
 *   formatTimestamp(Date.UTC(2021, 2, 26, 14, 5));            // '26 Mar 2021 14:05'
 *   formatTimestamp('2021-03-26', { precision: 'date' });       // '26 Mar 2021'
 *   formatTimestamp(Date.now(), { timeZone: 'local', precision: 'second' });
 *   formatIsoDay('2021-03-26T14:05:00Z');                       // '2021-03-26'
 *   formatShortDateTime('2021-03-26T14:05:00Z');                // 'Mar 26, 2:05 PM' (local)
 *   formatDuration(3660);                                       // '1h 1m'
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { EMPTY } from './number-format';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

export const MONTH_LABELS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

export const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

/** Rendered for a value that does not parse to a finite instant: the shared `EMPTY` glyph. */
export const INVALID_TIMESTAMP = EMPTY;

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type TimestampPrecision = 'date' | 'minute' | 'second';
export type TimestampTimeZone = 'utc' | 'local';
export type TimestampInput = number | string | Date;

/** Largest unit `formatDuration` rolls up to. */
export type DurationLargestUnit = 'h' | 'm';

export interface FormatDurationOptions {
  /** Default `'h'` (`1h 1m`); `'m'` keeps minutes past the hour (`61m 0s`). */
  largestUnit?: DurationLargestUnit | undefined;
  /** Label for a duration under one second; `null` floors it to whole seconds. Default `'<1s'`. */
  belowOneSecond?: string | null | undefined;
}

export interface FormatTimestampOptions {
  /** Default `'minute'`. */
  precision?: TimestampPrecision | undefined;
  /** Default `'utc'`. */
  timeZone?: TimestampTimeZone | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const pad2 = (value: number) => `${value}`.padStart(2, '0');

/** Parses any accepted input into a Date, or `null` when it is not a finite instant. */
export function toTimestampDate(value: TimestampInput): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

export function formatTimestamp(value: TimestampInput, opts: FormatTimestampOptions = {}): string {
  const date = toTimestampDate(value);
  if (!date) return INVALID_TIMESTAMP;
  const { precision = 'minute', timeZone = 'utc' } = opts;
  const utc = timeZone === 'utc';
  const day = utc ? date.getUTCDate() : date.getDate();
  const month = MONTH_LABELS[utc ? date.getUTCMonth() : date.getMonth()];
  const year = utc ? date.getUTCFullYear() : date.getFullYear();
  const dateText = `${pad2(day)} ${month} ${year}`;
  if (precision === 'date') return dateText;
  const hours = pad2(utc ? date.getUTCHours() : date.getHours());
  const minutes = pad2(utc ? date.getUTCMinutes() : date.getMinutes());
  if (precision === 'minute') return `${dateText} ${hours}:${minutes}`;
  const seconds = pad2(utc ? date.getUTCSeconds() : date.getSeconds());
  return `${dateText} ${hours}:${minutes}:${seconds}`;
}

/** A `YYYY-MM-DD` calendar day as local midnight (`new Date('2021-03-26')` would be UTC
    midnight, a day early west of Greenwich); an invalid day is an Invalid Date. */
export function parseLocalDay(value: string): Date {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year ?? Number.NaN, (month ?? 0) - 1, day ?? Number.NaN);
}

/** ISO calendar day (`2021-03-26`): a string's leading ten characters, a Date's UTC day. */
export function formatIsoDay(value: string | Date | null | undefined): string {
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? value.toISOString().slice(0, 10) : EMPTY;
  }
  return value ? value.slice(0, 10) : EMPTY;
}

/** Short local date-time (`Mar 26, 2:05 PM`); `empty` is rendered for a missing value. */
export function formatShortDateTime(
  value: string | null | undefined,
  empty: string = EMPTY,
): string {
  return value
    ? new Date(value).toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      })
    : empty;
}

/** Age relative to `now` (`just now`, `42s ago`, `5m ago`, `3h ago`, `2d ago`), then a
    short date past a week; `empty` for a missing or invalid value. */
export function formatRelativeTime(
  value: string | null | undefined,
  now: number = Date.now(),
  empty: string = EMPTY,
): string {
  const at = value ? Date.parse(value) : Number.NaN;
  if (!Number.isFinite(at)) return empty;
  const seconds = Math.max(0, Math.floor((now - at) / 1000));
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 7 * 86_400) return `${Math.floor(seconds / 86_400)}d ago`;
  return formatShortDateTime(value, empty);
}

/** Elapsed seconds as `45s`, `1m 1s` or `1h 1m`, or `EMPTY`. */
export function formatDuration(
  seconds: number | null | undefined,
  opts: FormatDurationOptions = {},
): string {
  if (seconds == null || !Number.isFinite(seconds)) return EMPTY;
  const { largestUnit = 'h', belowOneSecond = '<1s' } = opts;
  if (belowOneSecond !== null && seconds < 1) return belowOneSecond;
  const total = Math.floor(seconds);
  if (total < 60) return `${total}s`;
  if (largestUnit === 'm' || total < 3600) return `${Math.floor(total / 60)}m ${total % 60}s`;
  return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
}
