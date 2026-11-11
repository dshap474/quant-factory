/**
 * Loop-based min/max extent over data-sized numeric arrays.
 *
 * Spreading a data-sized array into Math.min/Math.max (`Math.max(...values)`)
 * overflows the argument stack on large series (RangeError: Maximum call
 * stack size exceeded). These helpers iterate instead, and skip null,
 * undefined, and NaN values explicitly.
 *
 * USAGE:
 *   import { extentBy, extentOf } from '@quant-factory/qf-ui';
 *   const ext = extentOf(values);                    // undefined when no usable value
 *   const ext = extentBy(points, (p) => p.value);
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface Extent {
  min: number;
  max: number;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Min/max of `value(item)` across items, skipping null/undefined/NaN. */
export function extentBy<T>(
  items: readonly T[],
  value: (item: T) => number | null | undefined,
): Extent | undefined {
  let min = Infinity;
  let max = -Infinity;
  let found = false;
  for (const item of items) {
    const candidate = value(item);
    if (candidate == null || Number.isNaN(candidate)) continue;
    found = true;
    if (candidate < min) min = candidate;
    if (candidate > max) max = candidate;
  }
  return found ? { min, max } : undefined;
}

/** Min/max of the values themselves, skipping null/undefined/NaN. */
export function extentOf(values: readonly (number | null | undefined)[]): Extent | undefined {
  return extentBy(values, (value) => value);
}
