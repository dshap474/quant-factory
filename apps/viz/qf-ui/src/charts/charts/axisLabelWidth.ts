/**
 * Width a value axis needs for its labels, so a linked stack can size one shared gutter.
 *
 * ECharts lays labels out after the option is applied, so the panes estimate up front:
 * sample the tick values the axis is likely to label, format them the way the axis will,
 * and measure the widest string in the axis font.
 *
 * USAGE:
 *   const width = axisLabelWidth({ domain: [0, 1], scale: 'linear', splitNumber: 3, format, fontSize: 12 });
 *   const drawn = visibleAxisLabelWidth({ domain: [0.03, 0.97], scale: 'linear', splitNumber: 5, format, fontSize: 12 });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { resolveChartFont } from '../theme/tokens';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface AxisLabelWidthOptions {
  /** Value range the axis plots; null when nothing is plotted yet. */
  domain: readonly [number, number] | null;
  scale: 'linear' | 'log';
  splitNumber: number;
  format: (value: number) => string;
  fontSize: number;
  /** The axis hides both end labels (linked panes), so only interior ticks need room. */
  hideExtremes?: boolean;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Average glyph advance, in ems, used when no canvas can measure text. */
const FALLBACK_GLYPH_EM = 0.6;

// --------------------------------------------------------------------------- #
// Tick sampling
// --------------------------------------------------------------------------- #

/** Rounds a raw interval to the 1 / 2 / 3 / 5 / 10 ladder ECharts uses for value axes. */
export function niceStep(rawStep: number): number {
  if (!(rawStep > 0) || !Number.isFinite(rawStep)) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const nice = residual < 1.5 ? 1 : residual < 2.5 ? 2 : residual < 4 ? 3 : residual < 7 ? 5 : 10;
  return nice * magnitude;
}

/**
 * Tick values an axis over `domain` is likely to label: the domain ends plus the nice
 * interior ticks for a value axis, or the powers of ten for a log axis.
 */
export function axisLabelSamples(
  domain: readonly [number, number] | null,
  scale: 'linear' | 'log',
  splitNumber: number,
): number[] {
  if (!domain) return [];
  const [rawMin, rawMax] = domain;
  if (!Number.isFinite(rawMin) || !Number.isFinite(rawMax)) return [];
  const min = Math.min(rawMin, rawMax);
  const max = Math.max(rawMin, rawMax);
  const samples = new Set<number>([min, max]);
  if (scale === 'log') {
    if (min > 0) {
      const first = Math.ceil(Math.log10(min));
      const last = Math.floor(Math.log10(max));
      for (let power = first; power <= last; power += 1) samples.add(10 ** power);
    }
    return [...samples];
  }
  // Ticks are whole multiples of the step: accumulating `tick += step` drifts, so a zero
  // tick lands on -5.55e-17 and formats as a phantom wide label ("-5.55e-15%").
  const step = niceStep((max - min) / Math.max(1, splitNumber));
  const last = Math.floor(max / step + 1e-9);
  for (let index = Math.ceil(min / step - 1e-9); index <= last; index += 1) {
    samples.add(Number((index * step).toPrecision(12)) || 0);
  }
  return [...samples];
}

/** ECharts' default number of value-axis intervals when the caller sets none. */
const DEFAULT_SPLIT_NUMBER = 5;

/** True when `value` sits on the tick ladder: a multiple of `step`, or a power of ten on a log axis. */
function onTickLadder(value: number, scale: 'linear' | 'log', step: number): boolean {
  if (scale === 'log') {
    if (!(value > 0)) return false;
    const power = Math.log10(value);
    return Math.abs(power - Math.round(power)) < 1e-9;
  }
  const ratio = value / step;
  return Math.abs(ratio - Math.round(ratio)) < 1e-6;
}

/**
 * Which extreme labels an axis over an explicit `domain` should draw.
 *
 * ECharts always labels the ends of an axis with a fixed min/max, so a padded domain
 * prints odd values (28.3K, $5.03) crowding the nearest nice tick. An end that is not
 * itself on the tick ladder is hidden, as long as nice ticks remain to label the axis.
 * Returns an empty object when both ends should keep ECharts' default behaviour.
 */
export function extremeLabelVisibility(
  domain: readonly [number, number] | undefined,
  scale: 'linear' | 'log',
  splitNumber: number = DEFAULT_SPLIT_NUMBER,
): { showMinLabel?: boolean; showMaxLabel?: boolean } {
  if (!domain) return {};
  const min = Math.min(domain[0], domain[1]);
  const max = Math.max(domain[0], domain[1]);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return {};
  const step = niceStep((max - min) / Math.max(1, splitNumber));
  const interior = axisLabelSamples([min, max], scale, splitNumber).filter(
    (value) => value > min && value < max,
  );
  if (interior.length < (scale === 'log' ? 1 : 2)) return {};
  const visibility: { showMinLabel?: boolean; showMaxLabel?: boolean } = {};
  if (!onTickLadder(min, scale, step)) visibility.showMinLabel = false;
  if (!onTickLadder(max, scale, step)) visibility.showMaxLabel = false;
  return visibility;
}

// --------------------------------------------------------------------------- #
// Measurement
// --------------------------------------------------------------------------- #

let measureContext: CanvasRenderingContext2D | null | undefined;

function canvasContext(): CanvasRenderingContext2D | null {
  if (measureContext !== undefined) return measureContext;
  measureContext = null;
  if (typeof document === 'undefined') return null;
  try {
    measureContext = document.createElement('canvas').getContext('2d');
  } catch {
    measureContext = null;
  }
  return measureContext;
}

/** Pixel width of the widest label in the axis font; estimated when no canvas exists. */
export function measureLabelWidth(labels: readonly string[], fontSize: number): number {
  if (labels.length === 0) return 0;
  const context = canvasContext();
  if (context) {
    // Measured in the face actually drawn: the token sans that QfChart's base text style applies.
    context.font = `${fontSize}px ${resolveChartFont()}`;
    return labels.reduce((widest, label) => Math.max(widest, context.measureText(label).width), 0);
  }
  const longest = labels.reduce((count, label) => Math.max(count, label.length), 0);
  return longest * fontSize * FALLBACK_GLYPH_EM;
}

/**
 * Width of the labels an axis over an explicit `domain` actually draws: the sampled
 * ticks minus any extreme that extremeLabelVisibility hides.
 */
export function visibleAxisLabelWidth({
  domain,
  scale,
  splitNumber,
  format,
  fontSize,
}: AxisLabelWidthOptions): number {
  if (!domain) return 0;
  const min = Math.min(domain[0], domain[1]);
  const max = Math.max(domain[0], domain[1]);
  const visibility = extremeLabelVisibility(domain, scale, splitNumber);
  const labels = axisLabelSamples(domain, scale, splitNumber)
    .filter(
      (value) =>
        !(value === min && visibility.showMinLabel === false) &&
        !(value === max && visibility.showMaxLabel === false),
    )
    .map((value) => format(value));
  return measureLabelWidth(labels, fontSize);
}

export function axisLabelWidth({
  domain,
  scale,
  splitNumber,
  format,
  fontSize,
  hideExtremes = false,
}: AxisLabelWidthOptions): number {
  let values = axisLabelSamples(domain, scale, splitNumber);
  if (hideExtremes && domain) {
    const min = Math.min(domain[0], domain[1]);
    const max = Math.max(domain[0], domain[1]);
    const interior = values.filter((value) => value > min && value < max);
    if (interior.length > 0) values = interior;
  }
  const labels = values.map((value) => format(value));
  return measureLabelWidth(labels, fontSize);
}
