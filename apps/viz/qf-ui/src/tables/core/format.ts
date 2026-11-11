/**
 * Pure column formatting helpers for tables (numeric detection, decimal scale, dtype labels).
 *
 * USAGE:
 *   const scale = columnDecimalScale([38470, 38470.16]); // 2
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ColumnFormat {
  /** Every non-null value on the page is a plain number rendered as a number. */
  numeric: boolean;
  /** Fixed decimal places applied to every numeric cell in the column. */
  scale: number;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const MAX_DECIMAL_SCALE = 8;

/**
 * Decimal places carried by a single finite number. Values are re-read at 12
 * significant digits first so IEEE-754 tails (29532084.18100001) do not widen a
 * whole column to eight decimals.
 */
export function decimalPlaces(value: number): number {
  if (!Number.isFinite(value) || Number.isInteger(value)) return 0;
  const text = String(Number(value.toPrecision(12)));
  if (text.includes('e')) return MAX_DECIMAL_SCALE;
  const dot = text.indexOf('.');
  if (dot < 0) return 0;
  return Math.min(text.length - dot - 1, MAX_DECIMAL_SCALE);
}

/** Max decimal scale seen across a page of values, so a column's decimals line up. */
export function columnDecimalScale(values: readonly unknown[]): number {
  let scale = 0;
  for (const value of values) {
    if (typeof value !== 'number') continue;
    scale = Math.max(scale, decimalPlaces(value));
  }
  return scale;
}

/** Classify a page of column values as numeric (right-aligned, fixed decimals) or not. */
export function columnFormat(values: readonly unknown[], temporal: boolean): ColumnFormat {
  if (temporal) return { numeric: false, scale: 0 };
  let sawNumber = false;
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value !== 'number' || !Number.isFinite(value)) return { numeric: false, scale: 0 };
    sawNumber = true;
  }
  if (!sawNumber) return { numeric: false, scale: 0 };
  return { numeric: true, scale: columnDecimalScale(values) };
}

const SCALAR_DTYPES: Record<string, string> = {
  Boolean: 'bool',
  Date: 'date',
  Float32: 'f32',
  Float64: 'f64',
  Int8: 'i8',
  Int16: 'i16',
  Int32: 'i32',
  Int64: 'i64',
  String: 'str',
  Time: 'time',
  UInt8: 'u8',
  UInt16: 'u16',
  UInt32: 'u32',
  UInt64: 'u64',
};

/** Short dtype label for the header's second line, e.g. `Float64` -> `f64`. */
export function compactDtype(dtype: string): string {
  const scalar = SCALAR_DTYPES[dtype];
  if (scalar) return scalar;
  const datetime = /^Datetime\(time_unit='(\w+)'(?:, time_zone=(?:'([^']+)'|None))?\)$/.exec(dtype);
  if (datetime) {
    const unit = datetime[1] === 'us' ? 'μs' : datetime[1];
    return datetime[2] ? `datetime[${unit}, ${datetime[2]}]` : `datetime[${unit}]`;
  }
  const duration = /^Duration\(time_unit='(\w+)'\)$/.exec(dtype);
  if (duration) return `duration[${duration[1] === 'us' ? 'μs' : duration[1]}]`;
  return dtype.toLowerCase();
}

const NUMERIC_DTYPE = /^(?:[iuf]\d+|u?int\d+|float\d+|decimal.*)$/i;

/** True for integer, float and decimal dtypes, compact (`i64`) or Polars (`Int64`) form. */
export function isNumericDtype(dtype: string | undefined): boolean {
  return dtype !== undefined && NUMERIC_DTYPE.test(dtype);
}

const GROUPED = new Map<number, Intl.NumberFormat>();

/** Fixed-scale number with thousands separators, e.g. `74637021.5679` at 2 -> `74,637,021.57`. */
export function formatGrouped(value: number, scale: number): string {
  let format = GROUPED.get(scale);
  if (!format) {
    format = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: scale,
      maximumFractionDigits: scale,
    });
    GROUPED.set(scale, format);
  }
  return format.format(value);
}
