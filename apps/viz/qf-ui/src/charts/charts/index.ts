/**
 * Public qf-charts chart exports.
 *
 * USAGE:
 *   import { LineChart, Heatmap } from '@quant-factory/qf-ui/charts/renderers';
 */

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export type { QfPoint, QfSeries, QfValueFormat } from '../types/contracts';
export {
  type AxisLabelWidthOptions,
  axisLabelSamples,
  axisLabelWidth,
  measureLabelWidth,
} from './axisLabelWidth';
export {
  CategoryBars,
  type CategoryBarsProps,
  type CategoryBarsSeries,
} from './CategoryBars';
export { Funnel, type FunnelDetail, type FunnelProps, type FunnelStage } from './Funnel';
export { Heatmap, type HeatmapCell, type HeatmapProps } from './Heatmap';
export { Histogram, type HistogramProps } from './Histogram';
export {
  echartsInterpolation,
  type QfEChartsInterpolation,
  type QfInterpolation,
  type QfLegacyCurve,
  resolveInterpolation,
} from './interpolation';
export {
  axisIndexForSeries,
  LineChart,
  type LineChartProps,
  normalizeLineSeries,
  primaryValueDomain,
  type QfAreaGradient,
  type QfAreaGradientStop,
  type QfLineMark,
  type QfLineModel,
  type QfLinePoint,
  type QfLineSeries,
  type QfXBand,
} from './LineChart';
export {
  MiniStackedBars,
  type MiniStackedBarsProps,
  type MiniStackedBarsSeries,
} from './MiniStackedBars';
export {
  MultiSeriesTimeChart,
  type MultiSeriesTimeChartProps,
} from './MultiSeriesTimeChart';
export {
  aggregateMarketBars,
  firstMarketBandTouch,
  type MarketBar,
  type MarketCandle,
  type MarketPriceBand,
  type MarketVolume,
  marketClosePoints,
} from './marketPriceLayers';
export {
  findNearestPoint,
  formatDateTick,
  formatTimeTick,
  formatTooltipDate,
  formatTooltipValue,
  formatYAxis,
  lttb,
  type MultiSeriesAxis,
  type MultiSeriesOverlay,
  type MultiSeriesPoint,
  type MultiSeriesSourcePoint,
  type MultiSeriesSourceSeries,
  type MultiSeriesValueFormat,
  upperBound,
} from './multiSeriesModel';
export {
  formatOptimizerValue,
  OptimizerGrid,
  type OptimizerGridDimension,
  type OptimizerGridFormat,
  type OptimizerGridMetric,
  type OptimizerGridProps,
  type OptimizerGridRow,
  type OptimizerGridSelection,
  optimizerValue,
} from './OptimizerGrid';
export { PortfolioDrawdownChart, type PortfolioDrawdownChartProps } from './PortfolioDrawdownChart';
export {
  PriceProfileChart,
  type PriceProfileChartProps,
  type PriceProfileDistribution,
  type PriceProfileFill,
  type PriceProfileFills,
  type PriceProfileLevel,
  type PriceProfileLine,
  type PriceProfileMarker,
  type PriceProfilePoint,
  type PriceProfileSegment,
  type PriceProfileTimeGuide,
} from './PriceProfileChart';
export { Sparkline, type SparklineProps } from './Sparkline';
export {
  StackedTimeChart,
  type StackedTimeChartProps,
  type StackedTimeMarker,
  type StackedTimeSeries,
} from './StackedTimeChart';
export {
  buildSegmentedAreaSeries,
  type SegmentedAreaPoint,
  type SegmentedAreaSegment,
  type SegmentedAreaSeriesOptions,
} from './segmentedAreaSeries';
export {
  TimelineChart,
  type TimelineChartProps,
  type TimelineRow,
} from './TimelineChart';
export {
  type CurveKind,
  TimeSeriesPlot,
  type TimeSeriesPlotProps,
  type TimeSeriesSeries,
} from './TimeSeriesPlot';
export {
  TransitionMatrix,
  type TransitionMatrixCell,
  type TransitionMatrixProps,
} from './TransitionMatrix';
export { Treemap, type TreemapNode, type TreemapProps } from './Treemap';
export {
  applyTimeSeriesTransforms,
  CHART_EMA_WINDOWS,
  CHART_Z_SCORE_WINDOWS,
  type ChartTransformControls,
  type ChartTransformState,
  type ChartTransformWindow,
  DEFAULT_CHART_TRANSFORM_STATE,
  exponentialMovingAverage,
  trailingZScore,
  transformedValueFormat,
} from './timeSeriesTransforms';
