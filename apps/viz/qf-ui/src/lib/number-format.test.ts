/**
 * Pins the shared number grammar.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/number-format.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import {
  EMPTY,
  formatBytes,
  formatCompact,
  formatCount,
  formatLocaleMoney,
  formatNumber,
  formatPercent,
  formatSignedMoney,
  formatSignedPercent,
  roundTo,
} from './number-format';
import { INVALID_TIMESTAMP } from './time-format';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('empty value', () => {
  it('shares one glyph with the time formatters', () => {
    expect(EMPTY).toBe('—');
    expect(INVALID_TIMESTAMP).toBe(EMPTY);
  });

  it('renders the glyph for absent and non-finite input', () => {
    for (const value of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(formatNumber(value)).toBe(EMPTY);
      expect(formatPercent(value)).toBe(EMPTY);
      expect(formatSignedPercent(value)).toBe(EMPTY);
      expect(formatCount(value)).toBe(EMPTY);
      expect(formatCompact(value)).toBe(EMPTY);
      expect(formatBytes(value)).toBe(EMPTY);
    }
    expect(roundTo(null, 2)).toBeNull();
  });
});

describe('fixed formats', () => {
  it('formats numbers, percents and counts', () => {
    expect(formatNumber(1.23456)).toBe('1.235');
    expect(formatNumber(1.23456, 1)).toBe('1.2');
    expect(formatPercent(0.0731, 2)).toBe('7.31%');
    expect(formatSignedPercent(0.0731)).toBe('+7.3%');
    expect(formatSignedPercent(0)).toBe('+0.0%');
    expect(formatSignedPercent(-0.02, 2)).toBe('-2.00%');
    expect(formatCount(12345, 'en-US')).toBe('12,345');
    expect(formatLocaleMoney(1234.5, 0)).toBe(
      `$${(1234.5).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
    );
    expect(formatSignedMoney(-56)).toBe('-$56');
    expect(formatSignedMoney(0)).toBe('$0');
    expect(formatSignedMoney(1234.5, 0)).toBe(
      `+$${(1234.5).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
    );
    expect(formatSignedMoney(null)).toBe(EMPTY);
  });
});

describe('formatCompact', () => {
  it('uses Intl compact notation by default', () => {
    expect(formatCompact(1234567, { currency: 'USD', maximumFractionDigits: 2 })).toBe('$1.23M');
    expect(formatCompact(1250, { maximumFractionDigits: 1 })).toBe('1.3K');
    expect(formatCompact(123456, { maximumSignificantDigits: 4 })).toBe('123.5K');
  });

  it('keeps trailing zeros on the fixed ladder', () => {
    const digits = { base: 0, K: 1, M: 2, B: 2 } as const;
    expect(formatCompact(999.6, { fixedDigits: digits, maxSuffix: 'B' })).toBe('1000');
    expect(formatCompact(12_000, { fixedDigits: digits, maxSuffix: 'B' })).toBe('12.0K');
    expect(formatCompact(1_500_000, { fixedDigits: digits, maxSuffix: 'B' })).toBe('1.50M');
    expect(formatCompact(2e12, { fixedDigits: digits, maxSuffix: 'B' })).toBe('2000.00B');
    expect(formatCompact(1234, { fixedDigits: 2, unit: 'SOL' })).toBe('1.23K SOL');
  });
});

describe('formatBytes', () => {
  it('rounds below a gigabyte and keeps one decimal above', () => {
    expect(formatBytes(512 * 1024 ** 2)).toBe('512 MB');
    expect(formatBytes(1536 * 1024 ** 2)).toBe('1.5 GB');
    expect(formatBytes(0.4 * 1024 ** 2, { minUnit: 'MB', maxUnit: 'GB' })).toBe('0 MB');
    expect(formatBytes(4096 * 1024 ** 3, { minUnit: 'MB', maxUnit: 'GB' })).toBe('4096.0 GB');
  });
});
