/**
 * Public qf-charts UI exports.
 *
 * USAGE:
 *   import { ChartFrame } from '@quant-factory/qf-ui/charts/chrome';
 */

// --------------------------------------------------------------------------- #
// Exports
// --------------------------------------------------------------------------- #

export { BrushBar, type BrushBarProps, type BrushPoint } from './BrushBar';
export { ChartFrame, type ChartFrameProps } from './ChartFrame';
export {
  ChartInfoPopover,
  type ChartInfoPopoverProps,
  type ChartInfoSection,
} from './ChartInfoPopover';
export {
  ChartKey,
  type ChartKeyItem,
  type ChartKeyProps,
  type ChartKeySeries,
  chartKeyItems,
} from './ChartKey';
export {
  ChartLegend,
  ChartLegendItem,
  type ChartLegendItemProps,
  type ChartLegendProps,
  legendItemClass,
} from './ChartLegend';
export { ChartLegendLabel, type ChartLegendLabelProps } from './ChartLegendLabel';
export { ChartNote, type ChartNoteProps } from './ChartNote';
export { ChartState, type ChartStateProps } from './ChartState';
export {
  ChartToggleGroup,
  type ChartToggleGroupProps,
  type ChartToggleOption,
  type ChartToolbarVariant,
} from './ChartToggleGroup';
export {
  ChartTooltip,
  type ChartTooltipHtmlOptions,
  type ChartTooltipItem,
  ChartTooltipItems,
  type ChartTooltipItemsProps,
  type ChartTooltipProps,
  chartTooltipHtml,
} from './ChartTooltip';
export {
  type ChartTransformGroupMember,
  ChartTransformGroupProvider,
  type ChartTransformGroupProviderProps,
  ChartTransformMasterToolbar,
  type ChartTransformMasterToolbarProps,
  useChartTransformGroupMember,
} from './ChartTransformGroup';
export {
  ChartTransformToolbar,
  type ChartTransformToolbarProps,
} from './ChartTransformToolbar';
export { LegendCollapseButton, type LegendCollapseButtonProps } from './LegendCollapseButton';
export {
  crosshairOffset,
  DEFAULT_PANE_GUTTER,
  dateAtOffset,
  leftInsetForLabelWidth,
  linkedPaneGrid,
  type MultiPaneGutter,
  type MultiPaneLink,
  type MultiPanePosition,
  panePosition,
  showsSharedAxis,
  useMultiPaneLink,
} from './MultiPaneContext';
export {
  buildMultiPaneRows,
  MultiPaneTimeSeriesChart,
  type MultiPaneTimeSeriesChartProps,
  type MultiPaneTimeSeriesPane,
  type MultiPaneTooltipSection,
} from './MultiPaneTimeSeriesChart';
export { TimeSeriesChart, type TimeSeriesChartProps } from './TimeSeriesChart';
