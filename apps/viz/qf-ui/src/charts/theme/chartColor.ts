/**
 * Named qf chart colours for hosts: pick a palette slot or a semantic tone by name,
 * optionally faded, without spelling CSS variable names or color-mix() strings.
 *
 * USAGE:
 *   import { chartColor } from '@quant-factory/qf-ui/charts/theme';
 *   chartColor(8);              // palette slot 8
 *   chartColor('positive');     // semantic tone
 *   chartColor('info', 0.58);   // tone at 58% opacity
 *   chartColor('foreground', 0.45); // primary text colour, faded (thresholds, outlines)
 *   chartStatusColor('critical');   // a qf-ui status Tone as a chart mark colour
 *   chartColor('neutral');      // muted neutral fill (quiet regimes, inactive bands)
 *   chartColor('baseline');     // the reference version a candidate is compared against
 *   chartPaletteColor(index);   // nth series colour, 0-based, cycling through the 20 slots
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { Tone } from '../../lib/tone';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** Palette slot, 1-20; slot 1 is the primary series colour. */
export type QfChartPaletteSlot =
  | 1
  | 2
  | 3
  | 4
  | 5
  | 6
  | 7
  | 8
  | 9
  | 10
  | 11
  | 12
  | 13
  | 14
  | 15
  | 16
  | 17
  | 18
  | 19
  | 20;

/** Semantic chart tone. */
export type QfChartTone =
  | 'positive'
  | 'negative'
  | 'info'
  | 'benchmark'
  | 'baseline'
  | 'label'
  | 'axis'
  | 'foreground'
  | 'neutral';

export type QfChartColorName = QfChartPaletteSlot | QfChartTone;

// --------------------------------------------------------------------------- #
// Colours
// --------------------------------------------------------------------------- #

const TONE_VARIABLE: Record<QfChartTone, string> = {
  positive: '--qf-chart-positive',
  negative: '--qf-chart-negative',
  info: '--qf-chart-tone-info',
  benchmark: '--qf-chart-benchmark',
  baseline: '--qf-chart-baseline',
  label: '--qf-chart-label',
  axis: '--qf-chart-axis',
  foreground: '--qf-chart-strong-text',
  neutral: '--qf-chart-neutral',
};

/** Fade any CSS colour to `opacity` (0-1); 1 or omitted returns the colour unchanged. */
export function withOpacity(color: string, opacity?: number): string {
  if (opacity == null || opacity >= 1) return color;
  const percent = Math.round(Math.max(0, opacity) * 100);
  return `color-mix(in oklch, ${color} ${percent}%, transparent)`;
}

/** CSS colour for a palette slot or semantic tone, optionally faded to `opacity`. */
export function chartColor(name: QfChartColorName, opacity?: number): string {
  const variable = typeof name === 'number' ? `--qf-chart-${name}` : TONE_VARIABLE[name];
  return withOpacity(`var(${variable})`, opacity);
}

/** Number of palette slots; `chartPaletteColor` cycles through them. */
export const CHART_PALETTE_SIZE = 20;

/** Colour for the `index`-th series (0-based), cycling through the palette slots. */
export function chartPaletteColor(index: number, opacity?: number): string {
  const slot = (((index % CHART_PALETTE_SIZE) + CHART_PALETTE_SIZE) % CHART_PALETTE_SIZE) + 1;
  return chartColor(slot as QfChartPaletteSlot, opacity);
}

/** Chart bridge for each status tone; `running` reads as info, as it does in StatusBadge. */
const STATUS_VARIABLE: Record<Tone | 'running', string> = {
  neutral: '--qf-chart-tone-neutral',
  info: '--qf-chart-tone-info',
  running: '--qf-chart-tone-info',
  success: '--qf-chart-positive',
  warning: '--qf-chart-tone-warning',
  critical: '--qf-chart-negative',
};

/** CSS colour for a qf-ui status `Tone` (or `running`) on a chart mark, optionally faded. */
export function chartStatusColor(tone: Tone | 'running', opacity?: number): string {
  return withOpacity(`var(${STATUS_VARIABLE[tone]})`, opacity);
}
