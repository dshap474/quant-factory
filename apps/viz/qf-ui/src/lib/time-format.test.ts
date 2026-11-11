/**
 * Pins the shared date grammar.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/time-format.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  formatDuration,
  formatIsoDay,
  formatShortDateTime,
  formatTimestamp,
  toTimestampDate,
} from './time-format';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

const INSTANT = Date.UTC(2021, 2, 26, 14, 5, 9);

describe('formatTimestamp', () => {
  it('defaults to minute precision in UTC', () => {
    expect(formatTimestamp(Date.UTC(2021, 2, 26, 14, 5))).toBe('26 Mar 2021 14:05');
  });

  it('formats date and second precision', () => {
    expect(formatTimestamp(INSTANT, { precision: 'date' })).toBe('26 Mar 2021');
    expect(formatTimestamp(INSTANT, { precision: 'second' })).toBe('26 Mar 2021 14:05:09');
  });

  it('accepts ISO strings and Date objects and pads the day', () => {
    expect(formatTimestamp('2024-07-05T00:00:00Z')).toBe('05 Jul 2024 00:00');
    expect(formatTimestamp(new Date(INSTANT), { precision: 'date' })).toBe('26 Mar 2021');
  });

  it('renders local time when asked', () => {
    const local = new Date(2021, 2, 26, 9, 30);
    expect(formatTimestamp(local, { timeZone: 'local' })).toBe('26 Mar 2021 09:30');
  });

  it('returns an em dash for an invalid value', () => {
    expect(formatTimestamp('not a date')).toBe('—');
    expect(formatTimestamp(Number.NaN)).toBe('—');
    expect(toTimestampDate('nope')).toBeNull();
  });
});

describe('formatDuration', () => {
  it('formats durations without claiming unknown time is zero', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(Number.NaN)).toBe('—');
    expect(formatDuration(0.2)).toBe('<1s');
    expect(formatDuration(61)).toBe('1m 1s');
    expect(formatDuration(3660)).toBe('1h 1m');
  });

  it('caps at minutes and floors sub-second values when asked', () => {
    const opts = { largestUnit: 'm', belowOneSecond: null } as const;
    expect(formatDuration(0.2, opts)).toBe('0s');
    expect(formatDuration(59.9, opts)).toBe('59s');
    expect(formatDuration(3725.5, opts)).toBe('62m 5s');
  });
});

describe('formatIsoDay', () => {
  it('keeps the calendar day of ISO strings and UTC Date objects', () => {
    expect(formatIsoDay('2021-03-26T14:05:09Z')).toBe('2021-03-26');
    expect(formatIsoDay(new Date(INSTANT))).toBe('2021-03-26');
  });

  it('returns an em dash for absent or invalid values', () => {
    expect(formatIsoDay(null)).toBe('—');
    expect(formatIsoDay('')).toBe('—');
    expect(formatIsoDay(new Date(Number.NaN))).toBe('—');
  });
});

describe('formatShortDateTime', () => {
  it('uses the caller fallback for an absent value', () => {
    expect(formatShortDateTime(null)).toBe('—');
    expect(formatShortDateTime(null, 'Not recorded')).toBe('Not recorded');
  });

  it('renders month, day and minute', () => {
    const expected = new Date(INSTANT).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
    expect(formatShortDateTime(new Date(INSTANT).toISOString())).toBe(expected);
  });
});
