/**
 * How a line joins its observations, and the ECharts series keys for each choice.
 *
 * Lines are linear by default. Held, position, count and regime data declare
 * `'step-end'` (the value holds until the next point). Smoothing is opt-in and the
 * shared frames label it "Smoothed".
 *
 * USAGE:
 *   const mode = resolveInterpolation(item.interpolation, props.interpolation, item.curve);
 *   const seriesKeys = { type: 'line', ...echartsInterpolation(mode) };
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type QfInterpolation = 'linear' | 'step-end' | 'step-start' | 'smooth';

/** @deprecated use interpolation (`QfInterpolation`); kept until `curve` is retired. */
export type QfLegacyCurve = 'monotone' | 'stepAfter';

export interface QfEChartsInterpolation {
  smooth: boolean;
  smoothMonotone?: 'x';
  step: false | 'start' | 'end';
}

// --------------------------------------------------------------------------- #
// Resolution
// --------------------------------------------------------------------------- #

/**
 * Precedence: the series' interpolation, then the component's, then the legacy curve
 * (`stepAfter` is step-end, `monotone` is smooth), then linear.
 */
export function resolveInterpolation(
  series?: QfInterpolation,
  component?: QfInterpolation,
  curve?: QfLegacyCurve,
): QfInterpolation {
  if (series) return series;
  if (component) return component;
  if (curve === 'stepAfter') return 'step-end';
  if (curve === 'monotone') return 'smooth';
  return 'linear';
}

export function echartsInterpolation(mode: QfInterpolation): QfEChartsInterpolation {
  switch (mode) {
    case 'step-end':
      return { smooth: false, step: 'end' };
    case 'step-start':
      return { smooth: false, step: 'start' };
    case 'smooth':
      // Monotone smoothing never overshoots a local extreme between two points.
      return { smooth: true, smoothMonotone: 'x', step: false };
    default:
      return { smooth: false, step: false };
  }
}
