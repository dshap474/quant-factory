/**
 * Fast-changing pointer overlay for package-owned multi-series geometry.
 *
 * USAGE:
 *   <MultiSeriesPlotHost geometry={<MultiSeriesLinePlot … />} hoverPoints={points} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, type RefObject, useLayoutEffect, useRef, useState } from 'react';
import { type MultiSeriesHoverDot, MultiSeriesHoverOverlay } from '../charts/MultiSeriesLinePlot';
import {
  findNearestPoint,
  formatTooltipValue,
  type MultiSeriesOverlay,
  type MultiSeriesPlotSeries,
  type MultiSeriesValueAxis,
  type MultiSeriesValueFormat,
  upperBound,
  valueToPlotY,
} from '../charts/multiSeriesModel';
import { containTooltipAtCursor } from '../core/tooltip';
import { useRafState } from '../hooks/useRafState';
import { ChartTooltip, type ChartTooltipItem } from './ChartTooltip';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** Value axes the geometry plots against, so hover dots land on the drawn lines. */
export interface MultiSeriesHoverAxes {
  left: MultiSeriesValueAxis;
  right: MultiSeriesValueAxis;
  tertiary: MultiSeriesValueAxis;
  overlay: MultiSeriesValueAxis;
}

interface MultiSeriesPlotHostProps {
  geometry: ReactNode;
  hoverPoints: readonly { date: Date }[];
  innerHeight: number;
  innerWidth: number;
  marginLeft: number;
  marginTop: number;
  overlayColor: string;
  plotHeight: number;
  plotHostRef: RefObject<HTMLDivElement | null>;
  plotWidth: number;
  priceOverlay: MultiSeriesOverlay | null;
  series: readonly MultiSeriesPlotSeries[];
  tooltipMaxDistanceMs?: number;
  valueFormat?: MultiSeriesValueFormat;
  overlayValueFormat?: MultiSeriesValueFormat;
  xDomain: readonly [Date, Date];
  /** Omit to draw the hover line without per-series dots. */
  valueAxes?: MultiSeriesHoverAxes;
}

interface PlotPointer {
  point: readonly [number, number];
  visibleLeft: number;
  visibleWidth: number;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MultiSeriesPlotHost({
  geometry,
  hoverPoints,
  innerHeight,
  innerWidth,
  marginLeft,
  marginTop,
  overlayColor,
  plotHeight,
  plotHostRef,
  plotWidth,
  priceOverlay,
  series,
  tooltipMaxDistanceMs,
  xDomain,
  valueFormat = 'number',
  overlayValueFormat = 'number',
  valueAxes,
}: MultiSeriesPlotHostProps) {
  const [pointer, schedulePointer, clearPointer] = useRafState<PlotPointer | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [tooltipSize, setTooltipSize] = useState<readonly [number, number]>([220, 0]);
  const pointerX = pointer?.point[0] ?? null;

  const hoverDate = (() => {
    if (pointerX == null || hoverPoints.length === 0) return null;
    const start = xDomain[0].getTime();
    const end = xDomain[1].getTime();
    const ratio = (pointerX - marginLeft) / Math.max(innerWidth, 1);
    const target = start + ratio * (end - start);
    const index = upperBound(hoverPoints, target);
    const previous = hoverPoints[index - 1];
    const next = hoverPoints[index];
    if (!previous) return next?.date ?? null;
    if (!next) return previous.date;
    return Math.abs(next.date.getTime() - target) < Math.abs(previous.date.getTime() - target)
      ? next.date
      : previous.date;
  })();

  const hoverLineX = hoverDate
    ? marginLeft +
      ((hoverDate.getTime() - xDomain[0].getTime()) /
        Math.max(xDomain[1].getTime() - xDomain[0].getTime(), 1)) *
        innerWidth
    : null;
  const hoverDots: MultiSeriesHoverDot[] = [];
  const pushDot = (
    key: string,
    value: number,
    axis: MultiSeriesValueAxis | undefined,
    color: string,
  ) => {
    if (!axis || hoverLineX == null) return;
    const y = valueToPlotY(value, axis, marginTop, innerHeight);
    if (y != null) hoverDots.push({ key, x: hoverLineX, y, color });
  };

  const tooltipItems: ChartTooltipItem[] = hoverDate
    ? series.flatMap((item) => {
        const point = findNearestPoint(item.points, hoverDate, tooltipMaxDistanceMs);
        if (point && point.value !== null) {
          pushDot(
            item.metric,
            point.value,
            item.isBenchmark ? valueAxes?.overlay : valueAxes?.[item.axis],
            item.isBenchmark ? overlayColor : item.color,
          );
        }
        return point && point.value !== null
          ? [
              {
                label: item.label,
                value: formatTooltipValue(point.value, item.valueFormat ?? valueFormat),
                swatch: item.isBenchmark ? overlayColor : item.color,
              },
            ]
          : [];
      })
    : [];

  if (hoverDate && priceOverlay) {
    const overlayPoint = findNearestPoint(priceOverlay.points, hoverDate, tooltipMaxDistanceMs);
    if (overlayPoint && overlayPoint.value !== null) {
      pushDot(priceOverlay.id, overlayPoint.value, valueAxes?.overlay, overlayColor);
      tooltipItems.push({
        label: priceOverlay.label,
        value: formatTooltipValue(overlayPoint.value, overlayValueFormat),
        swatch: overlayColor,
      });
    }
  }

  const tooltipPosition = pointer
    ? (() => {
        const contained = containTooltipAtCursor(
          [pointer.point[0] - pointer.visibleLeft, pointer.point[1]],
          tooltipSize,
          [pointer.visibleWidth, plotHeight],
        );
        return [contained[0] + pointer.visibleLeft, contained[1]] as const;
      })()
    : null;

  useLayoutEffect(() => {
    const tooltip = tooltipRef.current;
    if (!tooltip) return;
    const nextSize = [tooltip.offsetWidth, tooltip.offsetHeight] as const;
    setTooltipSize((current) =>
      current[0] === nextSize[0] && current[1] === nextSize[1] ? current : nextSize,
    );
  });

  return (
    <div
      ref={plotHostRef}
      className="plot-host"
      onPointerMove={(event) => {
        const host = plotHostRef.current;
        if (!host) return;
        const bounds = host.getBoundingClientRect();
        const scrollport = host.closest<HTMLElement>('.multi-series-frame-scroll');
        const nextX = event.clientX - bounds.left;
        const nextY = event.clientY - bounds.top;
        schedulePointer({
          point: [
            Math.min(Math.max(nextX, marginLeft), marginLeft + innerWidth),
            Math.min(Math.max(nextY, 0), plotHeight),
          ],
          visibleLeft: scrollport?.scrollLeft ?? 0,
          visibleWidth: scrollport?.clientWidth ?? plotWidth,
        });
      }}
      onPointerLeave={() => clearPointer(null)}
    >
      {geometry}
      <MultiSeriesHoverOverlay
        plotWidth={plotWidth}
        plotHeight={plotHeight}
        hoverLineX={hoverLineX}
        marginTop={marginTop}
        innerHeight={innerHeight}
        dots={hoverDots}
      />
      {hoverDate && tooltipItems.length > 0 && hoverLineX != null && tooltipPosition ? (
        <div
          ref={tooltipRef}
          className="multi-tooltip"
          style={{
            transform: `translate3d(${tooltipPosition[0]}px, ${tooltipPosition[1]}px, 0)`,
          }}
        >
          <ChartTooltip date={hoverDate} items={tooltipItems} />
        </div>
      ) : null}
    </div>
  );
}
