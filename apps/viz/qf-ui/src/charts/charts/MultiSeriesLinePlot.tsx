/**
 * Multi-series geometry adapter over the package-owned line renderer.
 *
 * USAGE:
 *   <MultiSeriesLinePlot plotHeight={360} series={series} visibleSeries={series} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { QfInterpolation } from './interpolation';
import { LineChart } from './LineChart';
import {
  formatYAxis,
  type MultiSeriesOverlay,
  type MultiSeriesPlotSeries,
  type MultiSeriesValueFormat,
} from './multiSeriesModel';
import './MultiSeriesTimeChart.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface MultiSeriesLinePlotProps {
  plotWidth: number;
  plotHeight: number;
  marginLeft: number;
  marginTop: number;
  innerWidth: number;
  innerHeight: number;
  xDomain: readonly [Date, Date];
  leftDomain: readonly [number, number];
  rightDomain: readonly [number, number];
  tertiaryDomain?: readonly [number, number];
  overlayDomain: readonly [number, number];
  series: readonly MultiSeriesPlotSeries[];
  hiddenSeries: ReadonlySet<string>;
  emphasizedSeries: string | null;
  visibleSeries: readonly MultiSeriesPlotSeries[];
  visiblePriceOverlay?: MultiSeriesOverlay | null;
  valueFormat?: MultiSeriesValueFormat;
  leftValueFormat?: MultiSeriesValueFormat;
  rightValueFormat?: MultiSeriesValueFormat;
  tertiaryValueFormat?: MultiSeriesValueFormat;
  axisLabels?: { left?: string; right?: string; tertiary?: string };
  yScaleType?: 'linear' | 'log';
  /** How every line joins its points unless a series sets its own. */
  interpolation?: QfInterpolation;
}

/** Radius of the hover dots, matching the ECharts line renderer's 10px point dots. */
const HOVER_DOT_RADIUS = 5;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MultiSeriesLinePlot({
  plotWidth,
  plotHeight,
  marginLeft,
  marginTop,
  innerWidth,
  innerHeight,
  xDomain,
  leftDomain,
  rightDomain,
  tertiaryDomain = [0, 1],
  overlayDomain,
  series,
  hiddenSeries,
  emphasizedSeries,
  visibleSeries,
  visiblePriceOverlay = null,
  valueFormat = 'number',
  leftValueFormat = valueFormat,
  rightValueFormat = valueFormat,
  tertiaryValueFormat = 'number',
  axisLabels,
  yScaleType = 'linear',
  interpolation,
}: MultiSeriesLinePlotProps) {
  const hasBenchmark =
    visibleSeries.some((item) => item.isBenchmark) || visiblePriceOverlay !== null;
  return (
    <LineChart
      series={[
        ...series.map((item) => ({
          key: item.metric,
          label: item.label,
          points: item.points,
          color: item.color,
          axis:
            item.axis === 'right'
              ? ('secondary' as const)
              : item.axis === 'tertiary'
                ? ('tertiary' as const)
                : ('primary' as const),
          ...(item.isBenchmark === undefined ? {} : { isBenchmark: item.isBenchmark }),
          ...(item.interpolation === undefined ? {} : { interpolation: item.interpolation }),
          opacity: item.opacity ?? 1,
        })),
        ...(visiblePriceOverlay
          ? [
              {
                key: visiblePriceOverlay.id,
                label: visiblePriceOverlay.label,
                points: visiblePriceOverlay.points,
                isBenchmark: true,
              },
            ]
          : []),
      ]}
      height={plotHeight}
      hiddenSeries={hiddenSeries}
      emphasizedSeries={emphasizedSeries}
      className="plot-svg"
      ariaLabel="Dataset time series chart"
      xDomain={xDomain}
      yDomain={leftDomain}
      yScaleType={yScaleType}
      ySecondaryDomain={rightDomain}
      yTertiaryDomain={tertiaryDomain}
      yAxisInverse={valueFormat === 'rank'}
      ySecondaryAxisInverse={valueFormat === 'rank'}
      {...(hasBenchmark ? { benchmarkDomain: overlayDomain } : {})}
      {...(visiblePriceOverlay ? { benchmarkScaleType: 'log' as const } : {})}
      yFormat={(value) => formatYAxis(value, leftValueFormat)}
      ySecondaryFormat={(value) => formatYAxis(value, rightValueFormat)}
      yTertiaryFormat={(value) => formatYAxis(value, tertiaryValueFormat)}
      {...(axisLabels?.left === undefined ? {} : { yAxisName: axisLabels.left })}
      {...(axisLabels?.right === undefined ? {} : { ySecondaryAxisName: axisLabels.right })}
      {...(axisLabels?.tertiary === undefined ? {} : { yTertiaryAxisName: axisLabels.tertiary })}
      visibleTertiaryAxis={visibleSeries.some(
        (item) => item.axis === 'tertiary' && !item.isBenchmark,
      )}
      visibleSecondaryAxis={visibleSeries.some(
        (item) => item.axis === 'right' && !item.isBenchmark,
      )}
      padding={{
        top: marginTop,
        right: Math.max(plotWidth - marginLeft - innerWidth, 0),
        bottom: Math.max(plotHeight - marginTop - innerHeight, 0),
        left: marginLeft,
      }}
      tooltip={false}
      preservePlotGeometry
      {...(interpolation === undefined ? {} : { interpolation })}
    />
  );
}

export interface MultiSeriesHoverDot {
  key: string;
  x: number;
  y: number;
  color: string;
}

export function MultiSeriesHoverOverlay({
  plotWidth,
  plotHeight,
  hoverLineX,
  marginTop,
  innerHeight,
  dots = [],
}: {
  plotWidth: number;
  plotHeight: number;
  hoverLineX: number | null;
  marginTop: number;
  innerHeight: number;
  /** Where each series crosses the hover line, in plot pixels. */
  dots?: readonly MultiSeriesHoverDot[];
}) {
  if (hoverLineX == null) return null;
  return (
    <svg
      className="plot-svg plot-hover-overlay"
      viewBox={`0 0 ${Math.max(plotWidth, 1)} ${Math.max(plotHeight, 1)}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <line
        x1={hoverLineX}
        x2={hoverLineX}
        y1={marginTop}
        y2={marginTop + innerHeight}
        className="hover-line"
      />
      {dots.map((dot) => (
        <circle
          key={dot.key}
          cx={dot.x}
          cy={dot.y}
          r={HOVER_DOT_RADIUS}
          // An inline style resolves CSS-variable colours; the `fill` attribute would not.
          style={{ fill: dot.color }}
          className="hover-dot"
        />
      ))}
    </svg>
  );
}
