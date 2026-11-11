/**
 * Number display formatters: one `EMPTY` glyph and one implementation per format
 * shape, so a missing value reads identically everywhere. Every helper guards
 * non-finite input and falls back to `EMPTY` rather than rendering `NaN`,
 * `Infinity`, or a bare `-1`.
 *
 * USAGE:
 *   import { EMPTY, formatCompact, formatNumber, formatPercent } from '@quant-factory/qf-ui';
 *   formatNumber(1.23456);                                   // '1.235'
 *   formatNumber(null);                                      // '—'
 *   formatPercent(0.0731, 2);                                // '7.31%'
 *   formatSignedPercent(0.0731);                             // '+7.3%'
 *   formatCount(12345, 'en-US');                             // '12,345'
 *   formatCompact(1234567, { currency: 'USD' });             // '$1.23M'
 *   formatCompact(1234, { fixedDigits: 2, unit: 'SOL' });    // '1.23K SOL'
 *   formatBytes(72_000_000_000);                             // '67.1 GB'
 */

// --------------------------------------------------------------------------- #
// Empty value
// --------------------------------------------------------------------------- #

/** The single "no value" glyph (em dash) rendered for an absent or unusable value. */
export const EMPTY = '—';

// --------------------------------------------------------------------------- #
// Numeric helpers
// --------------------------------------------------------------------------- #

/** True when `value` is a real, finite number worth formatting. */
function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Round for display; returns `null` for absent or non-finite input so callers
 * (notably DataTable, which aligns decimals across a column) keep a real gap.
 */
export function roundTo(value: number | null | undefined, digits: number): number | null {
  if (!isFiniteNumber(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

/** Fixed-decimal number, or `EMPTY`. */
export function formatNumber(value: number | null | undefined, digits = 3): string {
  return isFiniteNumber(value) ? value.toFixed(digits) : EMPTY;
}

/** Signed fixed-decimal number with an optional unit (`+1.25`, `-0.4 pp`), or `EMPTY`. */
export function formatSignedNumber(
  value: number | null | undefined,
  digits = 2,
  suffix = '',
): string {
  if (!isFiniteNumber(value)) return EMPTY;
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}${suffix}`;
}

/** Locale-grouped integer count (`12,345`), or `EMPTY`; `locale` defaults to the runtime's. */
export function formatCount(value: number | null | undefined, locale?: string): string {
  return isFiniteNumber(value) ? value.toLocaleString(locale) : EMPTY;
}

// --------------------------------------------------------------------------- #
// Percent helpers
// --------------------------------------------------------------------------- #

/** Fraction rendered as a percentage, or `EMPTY`. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  return isFiniteNumber(value) ? `${(value * 100).toFixed(digits)}%` : EMPTY;
}

/** Fraction rendered as a signed percentage (`+7.3%`, `-2.0%`), or `EMPTY`. */
export function formatSignedPercent(value: number | null | undefined, digits = 1): string {
  if (!isFiniteNumber(value)) return EMPTY;
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
}

// --------------------------------------------------------------------------- #
// Money helpers
// --------------------------------------------------------------------------- #

/** Plain USD amount, or `EMPTY`. */
export function formatMoney(value: number | null | undefined, digits = 2): string {
  return isFiniteNumber(value) ? `$${value.toFixed(digits)}` : EMPTY;
}

/** Locale-grouped USD amount with a bounded fraction (`$12,345`), or `EMPTY`. */
export function formatLocaleMoney(
  value: number | null | undefined,
  maximumFractionDigits = 2,
): string {
  if (!isFiniteNumber(value)) return EMPTY;
  return `$${value.toLocaleString(undefined, { maximumFractionDigits })}`;
}

/** Locale-grouped signed USD amount (`+$1,234`, `-$56`), or `EMPTY`; zero is unsigned. */
export function formatSignedMoney(
  value: number | null | undefined,
  maximumFractionDigits = 2,
): string {
  if (!isFiniteNumber(value)) return EMPTY;
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits })}`;
}

// --------------------------------------------------------------------------- #
// Price helpers
// --------------------------------------------------------------------------- #

/**
 * Thousands-abbreviated USD price for dense chart axes and tooltips
 * (`$1.2k`, `$64k`, `$873`).
 */
export function formatAbbreviatedPrice(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return EMPTY;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return `$${value.toFixed(0)}`;
}

/** Locale-grouped price with a bounded fraction, for level and gap labels. */
export function formatLocalePrice(
  value: number | null | undefined,
  maximumFractionDigits = 1,
): string {
  if (!isFiniteNumber(value)) return EMPTY;
  return value.toLocaleString(undefined, { maximumFractionDigits });
}

/**
 * Micro-cap token price: fixed decimals down to 1e-4, exponential below, and an
 * exact `0` for a true zero.
 */
export function formatMicroPrice(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) return EMPTY;
  if (value === 0) return '0';
  return Math.abs(value) >= 1e-4 ? value.toFixed(6) : value.toExponential(2);
}

// --------------------------------------------------------------------------- #
// Compact helpers
// --------------------------------------------------------------------------- #

/** Magnitude suffix of the fixed compact ladder. */
export type CompactSuffix = 'K' | 'M' | 'B' | 'T';

/** Fraction digits of the fixed ladder: one count for every tier, or per tier. */
export type CompactFixedDigits = number | Partial<Record<'base' | CompactSuffix, number>>;

/** Intl compact notation (`1.2K`, `$3.45M`); trailing zeros are trimmed. */
export interface CompactIntlOptions {
  /** ISO 4217 code rendered with the currency symbol, e.g. `'USD'`. */
  currency?: string;
  maximumFractionDigits?: number;
  maximumSignificantDigits?: number;
  /** Appended after a space, e.g. `'SOL'`. */
  unit?: string;
  fixedDigits?: never;
  maxSuffix?: never;
}

/**
 * Fixed ladder (`1.50M`, `12.0K`): `toFixed` decimals per tier, trailing zeros kept,
 * so neighbouring axis ticks share one precision.
 */
export interface CompactFixedOptions {
  fixedDigits: CompactFixedDigits;
  /** Largest suffix used; bigger values keep scaling under it. Default `'T'`. */
  maxSuffix?: CompactSuffix;
  /** Appended after a space, e.g. `'SOL'`. */
  unit?: string;
  currency?: never;
  maximumFractionDigits?: never;
  maximumSignificantDigits?: never;
}

export type FormatCompactOptions = CompactIntlOptions | CompactFixedOptions;

const COMPACT_TIERS: ReadonlyArray<{ suffix: CompactSuffix; scale: number }> = [
  { suffix: 'K', scale: 1e3 },
  { suffix: 'M', scale: 1e6 },
  { suffix: 'B', scale: 1e9 },
  { suffix: 'T', scale: 1e12 },
];

const compactFormatters = new Map<string, Intl.NumberFormat>();

function compactFormatter(options: CompactIntlOptions): Intl.NumberFormat {
  const { currency, maximumFractionDigits, maximumSignificantDigits } = options;
  const key = `${currency ?? ''}|${maximumFractionDigits ?? ''}|${maximumSignificantDigits ?? ''}`;
  let formatter = compactFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat('en-US', {
      notation: 'compact',
      ...(currency ? { style: 'currency', currency } : {}),
      ...(maximumFractionDigits == null ? {} : { maximumFractionDigits }),
      ...(maximumSignificantDigits == null ? {} : { maximumSignificantDigits }),
    });
    compactFormatters.set(key, formatter);
  }
  return formatter;
}

function tierDigits(digits: CompactFixedDigits, tier: 'base' | CompactSuffix): number {
  return typeof digits === 'number' ? digits : (digits[tier] ?? 0);
}

function formatFixedCompact(value: number, options: CompactFixedOptions): string {
  const maxIndex = COMPACT_TIERS.findIndex((tier) => tier.suffix === (options.maxSuffix ?? 'T'));
  const magnitude = Math.abs(value);
  for (let index = maxIndex; index >= 0; index -= 1) {
    const tier = COMPACT_TIERS[index];
    if (tier && magnitude >= tier.scale) {
      const digits = tierDigits(options.fixedDigits, tier.suffix);
      return `${(value / tier.scale).toFixed(digits)}${tier.suffix}`;
    }
  }
  return value.toFixed(tierDigits(options.fixedDigits, 'base'));
}

/** Compact magnitude (`1.2K`, `$3.45M`, `1.50M SOL`), or `EMPTY`. */
export function formatCompact(
  value: number | null | undefined,
  options: FormatCompactOptions = {},
): string {
  if (!isFiniteNumber(value)) return EMPTY;
  const text =
    options.fixedDigits == null
      ? compactFormatter(options).format(value)
      : formatFixedCompact(value, options);
  return options.unit ? `${text} ${options.unit}` : text;
}

// --------------------------------------------------------------------------- #
// Byte helpers
// --------------------------------------------------------------------------- #

/** Binary (1024) storage unit. */
export type ByteUnit = 'B' | 'KB' | 'MB' | 'GB' | 'TB';

export interface FormatBytesOptions {
  /** Smallest unit shown; smaller sizes render as a fraction of it. Default `'B'`. */
  minUnit?: ByteUnit;
  /** Largest unit shown; bigger sizes keep scaling under it. Default `'TB'`. */
  maxUnit?: ByteUnit;
}

const BYTE_UNITS: readonly ByteUnit[] = ['B', 'KB', 'MB', 'GB', 'TB'];
const GIGABYTE_INDEX = 3;

/**
 * Storage size in binary units: whole numbers below a gigabyte (`512 MB`), one
 * decimal from a gigabyte up (`67.0 GB`), or `EMPTY`.
 */
export function formatBytes(
  bytes: number | null | undefined,
  options: FormatBytesOptions = {},
): string {
  if (!isFiniteNumber(bytes)) return EMPTY;
  const minIndex = BYTE_UNITS.indexOf(options.minUnit ?? 'B');
  const maxIndex = BYTE_UNITS.indexOf(options.maxUnit ?? 'TB');
  let index = minIndex;
  while (index < maxIndex && Math.abs(bytes) >= 1024 ** (index + 1)) index += 1;
  const scaled = bytes / 1024 ** index;
  const text = index >= GIGABYTE_INDEX ? scaled.toFixed(1) : String(Math.round(scaled));
  return `${text} ${BYTE_UNITS[index]}`;
}
