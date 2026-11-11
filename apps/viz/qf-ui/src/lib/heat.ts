/**
 * One heat scale for value-coloured cells (IC grids, correlation heatmaps, table
 * heat columns): the semantic chart tone faded by magnitude. Negative values take
 * the negative tone, positive values the positive tone, and `magnitude` scales
 * `|value|` on the info tone instead. Strength is `|value| / maxAbs` clamped to
 * 0-1 and maps linearly to 14%-88% opacity, so a zero still shows a faint tint
 * and a full-scale value stays readable under text. Missing values are
 * transparent.
 *
 * USAGE:
 *   divergingCellColor(0.04, { maxAbs: 0.08 });    // positive tone at 51%
 *   divergingCellColor(-0.3);                      // negative tone, maxAbs 1
 *   divergingCellColor(0.7, { magnitude: true });  // info tone at 66%
 *   <TableCell numeric heat={{ value, maxAbs }}>{formatNumber(value)}</TableCell>
 *   rankCellColor(0);     // best standing: success tone tint
 *   rankCellColor(0.5);   // middle: warning tone tint
 *   rankCellColor(null);  // singleton or all-equal cohort: transparent
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { chartColor } from '../charts/theme/chartColor';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DivergingCellColorOptions {
  /** Absolute value that takes full strength. Defaults to 1. */
  maxAbs?: number;
  /** Scale `|value|` on the info tone instead of diverging on sign. */
  magnitude?: boolean;
}

/** Declarative heat for a table cell: the value and its scale. */
export interface CellHeat extends DivergingCellColorOptions {
  value: number | null | undefined;
}

// --------------------------------------------------------------------------- #
// Scale
// --------------------------------------------------------------------------- #

export const HEAT_MIN_OPACITY = 0.14;
export const HEAT_MAX_OPACITY = 0.88;

/** CSS colour for one heat cell; `transparent` for a missing or non-finite value. */
export function divergingCellColor(
  value: number | null | undefined,
  { maxAbs = 1, magnitude = false }: DivergingCellColorOptions = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'transparent';
  const scale = maxAbs > 0 ? maxAbs : 1;
  const strength = Math.min(1, Math.abs(value) / scale);
  const opacity = HEAT_MIN_OPACITY + strength * (HEAT_MAX_OPACITY - HEAT_MIN_OPACITY);
  const tone = magnitude ? 'info' : value < 0 ? 'negative' : 'positive';
  return chartColor(tone, opacity);
}

// --------------------------------------------------------------------------- #
// Relative standing
// --------------------------------------------------------------------------- #

/** Fixed, restrained tint strength so primary text stays readable on every standing. */
export const RANK_TINT_PERCENT = 22;

/**
 * Background for a ranked cell: success (best, 0) through warning (0.5) to critical
 * (worst, 1). Position is relative standing, not absolute profitability; null or a
 * non-finite position is neutral (transparent).
 */
export function rankCellColor(position: number | null | undefined): string {
  if (position === null || position === undefined || !Number.isFinite(position)) {
    return 'transparent';
  }
  const clamped = Math.min(1, Math.max(0, position));
  const [from, to, share] =
    clamped <= 0.5
      ? ['success', 'warning', clamped * 2]
      : ['warning', 'critical', (clamped - 0.5) * 2];
  const stop = `color-mix(in oklab, var(--color-tone-${to}) ${Math.round(share * 100)}%, var(--color-tone-${from}))`;
  return `color-mix(in oklab, ${stop} ${RANK_TINT_PERCENT}%, transparent)`;
}
