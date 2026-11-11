/**
 * Time-axis tick label contract.
 *
 * USAGE:
 *   pnpm test -- tests/charts/time-axis-format.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  formatDateTick,
  formatTimeTick,
  formatTooltipDate,
} from '../../src/charts/charts/timeAxisFormat';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('formatDateTick', () => {
  const multiYear: readonly [Date, Date] = [new Date(2022, 0, 1), new Date(2026, 7, 31)];

  it('labels month starts with the month and year starts with the year', () => {
    expect(formatDateTick(new Date(2024, 6, 1), multiYear)).toBe('Jul');
    expect(formatDateTick(new Date(2025, 0, 1), multiYear)).toBe('2025');
  });

  it('labels other days with an unpadded day and month', () => {
    expect(formatDateTick(new Date(2024, 6, 15), multiYear)).toBe('15 Jul');
    expect(formatDateTick(new Date(2024, 6, 1, 12), multiYear)).toBe('1 Jul');
  });

  it('labels shorter spans with day and month', () => {
    const quarter: readonly [Date, Date] = [new Date(2024, 5, 1), new Date(2024, 6, 15)];
    expect(formatDateTick(new Date(2024, 6, 1), quarter)).toBe('Jul');
  });
});

describe('formatTimeTick', () => {
  const multiYear: readonly [Date, Date] = [new Date(2022, 0, 1), new Date(2026, 7, 31)];

  it('anchors the year on the first tick of a long span', () => {
    expect(formatTimeTick(new Date(2024, 6, 1), multiYear, 0)).toBe('Jul 2024');
    expect(formatTimeTick(new Date(2024, 6, 15), multiYear, 0)).toBe('15 Jul 2024');
    expect(formatTimeTick(new Date(2024, 6, 1), multiYear, 1)).toBe('Jul');
  });

  it('labels intraday spans with 24-hour times and a day landmark at midnight', () => {
    const intraday: readonly [Date, Date] = [new Date(2024, 6, 14, 12), new Date(2024, 6, 15, 12)];
    expect(formatTimeTick(new Date(2024, 6, 15, 0, 0), intraday)).toBe('15 Jul');
    expect(formatTimeTick(new Date(2024, 6, 15, 14, 0), intraday)).toBe('14:00');
  });
});

describe('formatTooltipDate', () => {
  it('renders a weekday day-month-year header for daily observations', () => {
    expect(formatTooltipDate(new Date(2021, 2, 26))).toBe('Fri 26 Mar 2021');
  });

  it('appends the clock time only for intraday observations', () => {
    expect(formatTooltipDate(new Date(2021, 2, 26, 14, 5))).toBe('Fri 26 Mar 2021 14:05');
  });

  it('does not pad a single-digit day', () => {
    expect(formatTooltipDate(new Date(2021, 2, 5))).toBe('Fri 5 Mar 2021');
  });
});
