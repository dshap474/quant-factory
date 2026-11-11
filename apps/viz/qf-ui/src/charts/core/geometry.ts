/**
 * Chart geometry constants importable without loading the ECharts runtime.
 *
 * USAGE:
 *   import { QF_CHART_ASPECT_RATIO, multiPaneAspectRatio } from '@quant-factory/qf-ui/charts/geometry';
 *   multiPaneAspectRatio(['main', 'study']); // 4:3, a 3:1 price-over-oscillator stack
 *   const left = valueGutterWidth(measuredLabelWidth);
 */

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

export const QF_CHART_ASPECT_RATIO = 16 / 9;

/**
 * Stroke width, in CSS pixels, of every plotted data line: series, areas' outlines,
 * benchmarks, comparisons, steps and sparklines, at rest and under hover alike. It is
 * the one width a renderer draws data at; series carry no width of their own.
 */
export const QF_CHART_LINE_WIDTH = 1.5;

/** Width of in-plot reference rules (zero, threshold and marker lines) and the crosshair. */
export const QF_CHART_RULE_WIDTH = 1;

/**
 * Card spacing in pixels, mirroring the --qf-chart-space-* tokens in qf-charts.css.
 * Every card edge keeps QF_CHART_INSET, so the title, the widest value label and the
 * brush track share one vertical line; tick labels sit QF_CHART_LABEL_GAP off the plot.
 */
export const QF_CHART_INSET = 16;
export const QF_CHART_LABEL_GAP = 8;
/** Band under the plot for time labels: gap, one 16px label line, gap. */
export const QF_CHART_TIME_AXIS_HEIGHT = QF_CHART_LABEL_GAP * 2 + 16;

/**
 * Height of each multi-pane row, in sixteenths of the frame width. A `main` pane is a
 * full 16:9 chart; a `study` pane (oscillator, volume, weight, drawdown) is a third of
 * that, the 3:1 main-to-indicator plot ratio of trading terminals.
 */
export type MultiPaneSize = 'main' | 'study';
export const QF_PANE_HEIGHT: Readonly<Record<MultiPaneSize, number>> = { main: 9, study: 3 };

/** A stack never grows taller than it is wide. */
const QF_STACK_MIN_ASPECT_RATIO = 1;

// --------------------------------------------------------------------------- #
// Gutters
// --------------------------------------------------------------------------- #

/**
 * Width of a value-axis gutter whose widest label measures `labelWidth` pixels: the
 * card inset, the label, and the label gap. With no measured label it keeps the inset.
 */
export function valueGutterWidth(labelWidth: number): number {
  const label = Number.isFinite(labelWidth) && labelWidth > 0 ? Math.ceil(labelWidth) : 0;
  return QF_CHART_INSET + label + (label > 0 ? QF_CHART_LABEL_GAP : 0);
}

/** Thickness of a rotated value-axis name set at `fontSize`. */
export function axisNameThickness(fontSize: number): number {
  return Math.ceil(fontSize * 1.2);
}

/** Extra gutter a rotated value-axis name needs: its thickness plus the label gap. */
export function axisNameBand(fontSize: number): number {
  return axisNameThickness(fontSize) + QF_CHART_LABEL_GAP;
}

// --------------------------------------------------------------------------- #
// Stacks
// --------------------------------------------------------------------------- #

/**
 * Aspect ratio of a multi-pane frame: the panes' heights stacked, so the main pane keeps
 * its standalone 16:9 height and each study adds a third of it, down to a square frame.
 *   ['main']                    16:9
 *   ['main', 'study']            4:3
 *   ['main', 'study', 'study']  16:15
 *   three studies, or two mains  1:1 (rows share the square in proportion)
 */
export function multiPaneAspectRatio(sizes: readonly (MultiPaneSize | undefined)[]): number {
  const height = sizes.reduce((sum, size) => sum + QF_PANE_HEIGHT[size ?? 'main'], 0);
  if (height <= 0) return QF_CHART_ASPECT_RATIO;
  return Math.max(QF_STACK_MIN_ASPECT_RATIO, 16 / height);
}
