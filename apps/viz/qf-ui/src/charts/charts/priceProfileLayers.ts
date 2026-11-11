/** Supplied time-series studies and explicit lifetime/event annotation layers.
 * USAGE: internal PriceProfileChart levelSeries / markerPoints builders.
 */
// --------------------------------------------------------------------------- #
// Imports and constants
// --------------------------------------------------------------------------- #
import { QF_CHART_LINE_WIDTH, QF_CHART_RULE_WIDTH } from '../core/geometry';
import type { QfChartTheme } from '../hooks/useChartTheme';
import { withOpacity } from '../theme/chartColor';
import { resolveCssColor } from '../theme/tokens';
import { crossSeries } from './priceProfileCrossSeries';
import { breakLineGaps } from './priceProfileModel';
import type {
  PriceProfileFills,
  PriceProfileLevel,
  PriceProfileMarker,
  PriceProfilePoint,
  PriceProfileSegment,
  PriceProfileTimeGuide,
} from './priceProfileTypes';

export const LEVEL_ID = 'level:';
const DASH: number[] = [4, 4];
const MARKER_SIZE = 10;
const MUTED_SEGMENT_OPACITY = 0.72;

// --------------------------------------------------------------------------- #
// Rendering layers
// --------------------------------------------------------------------------- #
export function lineSeries(id: string, name: string, color: string, data: PriceProfilePoint[]) {
  const lineStyle = { color, width: QF_CHART_LINE_WIDTH, type: 'solid' as const };
  return {
    id,
    name,
    type: 'line',
    xAxisIndex: 0,
    yAxisIndex: 0,
    data,
    showSymbol: false,
    connectNulls: false,
    smooth: false,
    clip: true,
    lineStyle,
    itemStyle: { color },
    emphasis: { disabled: true },
  };
}

export function levelSeries(
  level: PriceProfileLevel,
  color: string,
  maxGap: number | undefined,
  hidden: boolean,
  theme: QfChartTheme,
) {
  const points = hidden ? [] : breakLineGaps(level.points, maxGap);
  const cross = level.style === 'cross';
  const until = level.dashedUntil;
  const dashed = until == null ? [] : points.filter(([time]) => time <= until);
  const solid = until == null ? points : points.filter(([time]) => time >= until);
  // Older profile callers declare held levels through dashedUntil/endLabel.
  const interpolation =
    level.interpolation ??
    (level.dashedUntil != null || level.endLabel != null ? 'step-end' : 'linear');
  const width = level.weight === 'guide' ? QF_CHART_RULE_WIDTH : QF_CHART_LINE_WIDTH;
  const base = {
    step: interpolation === 'step-end' ? 'end' : false,
    smooth: interpolation === 'smooth',
    silent: true,
  };
  return [
    {
      ...lineSeries(`${LEVEL_ID}${level.key}:dashed`, level.label, color, cross ? [] : dashed),
      ...base,
      lineStyle: { color, width, type: DASH },
    },
    ...(cross
      ? [crossSeries(`${LEVEL_ID}${level.key}:solid`, level.label, color, points)]
      : [
          {
            ...lineSeries(`${LEVEL_ID}${level.key}:solid`, level.label, color, solid),
            ...base,
            lineStyle: { color, width, type: level.style ?? 'solid' },
            endLabel: {
              show: level.endLabel != null && solid.length > 0,
              formatter: level.endLabel ?? '',
              distance: 4,
              color,
              fontSize: theme.axisFontSize,
            },
            labelLayout: { moveOverlap: 'shiftY' },
          },
        ]),
  ];
}

export function segmentMarkLines(segments: readonly PriceProfileSegment[], theme: QfChartTheme) {
  return segments.map((segment) => {
    const color = resolveCssColor(
      segment.muted ? withOpacity(segment.color, MUTED_SEGMENT_OPACITY) : segment.color,
    );
    const lineStyle = {
      color,
      type: segment.style === 'dotted' ? ('dotted' as const) : DASH,
      width: segment.weight === 'level' ? QF_CHART_LINE_WIDTH : QF_CHART_RULE_WIDTH,
    };
    const label = segment.text
      ? {
          show: true,
          formatter: segment.text,
          position: segment.textPosition ?? 'end',
          color,
          fontSize: theme.axisFontSize,
        }
      : { show: false };
    return [
      {
        name: segment.label,
        coord: [segment.from, segment.value],
        symbol: 'none',
        lineStyle,
        label,
      },
      { name: segment.label, coord: [segment.to, segment.value], symbol: 'none', lineStyle },
    ];
  });
}

export function guideMarkLines(guides: readonly PriceProfileTimeGuide[], theme: QfChartTheme) {
  return guides.map((guide) => ({
    name: guide.label,
    xAxis: guide.at,
    lineStyle: {
      color: resolveCssColor(guide.color ?? theme.crosshair),
      type: 'dotted' as const,
      width: QF_CHART_RULE_WIDTH,
    },
    label: {
      show: Boolean(guide.label),
      formatter: guide.label,
      position: 'insideEndTop' as const,
      offset: [4, 4],
      align: 'left' as const,
      rotate: 0,
      color: theme.axis,
      fontSize: theme.axisFontSize,
    },
  }));
}

export function markerPoints(markers: readonly PriceProfileMarker[], theme: QfChartTheme) {
  return markers.map((marker) => {
    const color = resolveCssColor(marker.color);
    const fill = marker.role === 'entry' || marker.role === 'exit';
    const exit = marker.role === 'exit';
    const down = marker.side ? marker.side === 'sell' : exit || marker.role === 'exit_trigger';
    return {
      name: marker.key,
      coord: [marker.time, marker.value],
      value: marker.label,
      symbol:
        marker.role === 'signal' || marker.role === 'exit_trigger'
          ? 'diamond'
          : fill
            ? 'arrow'
            : 'circle',
      symbolRotate: down ? 180 : 0,
      symbolSize: fill ? 16 : MARKER_SIZE,
      symbolOffset: fill ? [0, down ? -18 : 18] : [0, 0],
      itemStyle: { color },
      label: {
        show: marker.role == null || fill,
        formatter: marker.label,
        position: marker.labelPosition ?? (fill ? (exit ? 'top' : 'bottom') : 'right'),
        color: marker.labelColor ? resolveCssColor(marker.labelColor) : color,
        backgroundColor: marker.labelBackdrop ? theme.background : undefined,
        padding: marker.labelBackdrop ? [2, 4] : undefined,
        fontSize: theme.axisFontSize,
      },
    };
  });
}

/** Fill dots: area proportional to size, solid or hollow, on the price axes. */
export const FILL_ID = 'fills';
const FILL_MIN_SIZE = 4;
const FILL_MAX_SIZE = 16;

export function fillSeries(fills: PriceProfileFills, color: string, hidden: boolean) {
  const largest = fills.points.reduce((max, point) => Math.max(max, point.size), 0) || 1;
  return {
    id: FILL_ID,
    name: fills.label,
    type: 'scatter',
    xAxisIndex: 0,
    yAxisIndex: 0,
    z: 4,
    silent: true,
    emphasis: { disabled: true },
    data: hidden
      ? []
      : fills.points.map((point) => ({
          value: [point.time, point.price],
          symbolSize:
            FILL_MIN_SIZE +
            (FILL_MAX_SIZE - FILL_MIN_SIZE) * Math.sqrt(Math.max(point.size, 0) / largest),
          itemStyle: point.solid
            ? { color, borderWidth: 0 }
            : { color: 'transparent', borderColor: color, borderWidth: QF_CHART_LINE_WIDTH },
        })),
  };
}
