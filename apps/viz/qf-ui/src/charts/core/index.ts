/**
 * Public qf-charts core exports.
 *
 * USAGE:
 *   import { QfChart } from '@quant-factory/qf-ui/charts/core';
 */

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export {
  type QfLifecycleEvent,
  type QfLifecycleRecorder,
  recordLifecycle,
  setLifecycleRecorder,
} from './diagnostics/lifecycle';
export {
  type MultiPaneSize,
  multiPaneAspectRatio,
  QF_CHART_INSET,
  QF_CHART_LABEL_GAP,
  QF_CHART_TIME_AXIS_HEIGHT,
  QF_PANE_HEIGHT,
  valueGutterWidth,
} from './geometry';
export {
  QF_CHART_ASPECT_RATIO,
  QfChart,
  type QfChartClickEvent,
  type QfChartOption,
  type QfChartProps,
} from './QfChart';
export { isChartRuntimeRegistered, registerCharts } from './registerCharts';
