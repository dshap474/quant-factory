/**
 * Builds one continuous area with hard color stops at segment transitions.
 *
 * USAGE:
 *   const series = buildSegmentedAreaSeries({ points, segments });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { QfInterpolation } from './interpolation';
import type { QfAreaGradientStop } from './LineChart';
import type { MultiSeriesPoint } from './multiSeriesModel';
import type { TimeSeriesSeries } from './TimeSeriesPlot';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SegmentedAreaPoint<TSegment extends string = string> extends MultiSeriesPoint {
  segment: TSegment | null;
}

export interface SegmentedAreaSegment<TSegment extends string = string> {
  id: TSegment;
  color: string;
}

export interface SegmentedAreaSeriesOptions<TSegment extends string = string> {
  points: readonly SegmentedAreaPoint<TSegment>[];
  segments: readonly SegmentedAreaSegment<TSegment>[];
  opacity?: number;
  /**
   * How the area joins its points. With `'step-end'` the colour changes where the step
   * happens (at the new segment's first point); otherwise midway between the two points.
   */
  interpolation?: QfInterpolation;
}

// --------------------------------------------------------------------------- #
// Gradient
// --------------------------------------------------------------------------- #

function gradientOffset(timestamp: number, start: number, end: number): number {
  if (end <= start) return 0;
  return Math.min(Math.max((timestamp - start) / (end - start), 0), 1);
}

// --------------------------------------------------------------------------- #
// Series construction
// --------------------------------------------------------------------------- #

export function buildSegmentedAreaSeries<TSegment extends string>({
  points,
  segments,
  opacity = 0.88,
  interpolation,
}: SegmentedAreaSeriesOptions<TSegment>): TimeSeriesSeries[] {
  const segmentStyles = new Map(segments.map((segment) => [segment.id, segment]));
  const firstPoint = points[0];
  const lastPoint = points.at(-1);
  const firstKnownPoint = points.find(
    (point) => point.segment != null && segmentStyles.has(point.segment),
  );
  let lastKnownPoint: SegmentedAreaPoint<TSegment> | undefined;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (point?.segment != null && segmentStyles.has(point.segment)) {
      lastKnownPoint = point;
      break;
    }
  }
  if (
    !firstPoint ||
    !lastPoint ||
    firstKnownPoint?.segment == null ||
    lastKnownPoint?.segment == null
  )
    return [];

  const firstStyle = segmentStyles.get(firstKnownPoint.segment);
  const lastStyle = segmentStyles.get(lastKnownPoint.segment);
  if (!firstStyle || !lastStyle) return [];

  const start = firstPoint.date.getTime();
  const end = lastPoint.date.getTime();
  const stops: QfAreaGradientStop[] = [{ offset: 0, color: firstStyle.color }];
  for (const [index, point] of points.entries()) {
    const previous = points[index - 1];
    if (!previous || previous.segment === point.segment || point.segment == null) continue;

    const currentStyle = segmentStyles.get(point.segment);
    if (!currentStyle) continue;

    if (previous.segment != null) {
      const previousStyle = segmentStyles.get(previous.segment);
      if (previousStyle) {
        const boundary =
          interpolation === 'step-end'
            ? point.date.getTime()
            : (previous.date.getTime() + point.date.getTime()) / 2;
        const offset = gradientOffset(boundary, start, end);
        stops.push({ offset, color: previousStyle.color }, { offset, color: currentStyle.color });
        continue;
      }
    }

    stops.push({
      offset: gradientOffset(point.date.getTime(), start, end),
      color: currentStyle.color,
    });
  }
  stops.push({ offset: 1, color: lastStyle.color });

  const data: MultiSeriesPoint[] = points.map((point) => ({
    date: point.date,
    value: point.value,
    active: point.segment != null && segmentStyles.has(point.segment),
  }));
  return [
    {
      id: 'segmented-area',
      data,
      color: firstStyle.color,
      showLine: false,
      area: true,
      areaBaseline: 'zero',
      areaFill: { stops },
      opacity,
      ...(interpolation === undefined ? {} : { interpolation }),
      defined: (point) => point.active === true,
    },
  ];
}
