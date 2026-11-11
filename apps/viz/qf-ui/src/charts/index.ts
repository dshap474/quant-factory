/**
 * Lightweight root entrypoint for common qf-charts contracts and components.
 *
 * USAGE:
 *   import { LineChart, type QfSeries } from '@quant-factory/qf-ui/charts';
 */

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export { displaySeries } from './charts/displaySeries';
export {
  LineChart,
  type LineChartProps,
  type QfLineMark,
  type QfLinePoint,
  type QfLineSeries,
  type QfXBand,
} from './charts/LineChart';
export {
  MultiSeriesTimeChart,
  type MultiSeriesTimeChartProps,
} from './charts/MultiSeriesTimeChart';
export {
  OrderbookDepthChart,
  type OrderbookDepthChartProps,
  type OrderbookHeatmapData,
  type OrderbookHistoricalScale,
  type OrderbookLevel,
  OrderbookLiquidityChart,
  type OrderbookLiquidityChartProps,
  type OrderbookScaleMode,
  type OrderbookSnapshot,
} from './charts/OrderbookChart';
export type {
  ChartTransformControls,
  ChartTransformState,
  ChartTransformWindow,
} from './charts/timeSeriesTransforms';
export { ChartFrame, type ChartFrameProps } from './components/ChartFrame';
export {
  ChartToggleGroup,
  type ChartToggleGroupProps,
  type ChartToggleOption,
  type ChartToolbarVariant,
} from './components/ChartToggleGroup';
export {
  ChartTransformGroupProvider,
  type ChartTransformGroupProviderProps,
  ChartTransformMasterToolbar,
  type ChartTransformMasterToolbarProps,
} from './components/ChartTransformGroup';
export {
  ChartTransformToolbar,
  type ChartTransformToolbarProps,
} from './components/ChartTransformToolbar';
export type { QfPadding, QfPoint, QfSeries, QfValueFormat } from './types/contracts';
