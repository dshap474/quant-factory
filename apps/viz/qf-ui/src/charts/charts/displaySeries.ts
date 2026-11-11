/**
 * Scale and accumulate complete time-series evidence before chart brushing.
 * USAGE: displaySeries(points, { scale: -1, cumulative: true });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { MultiSeriesNullableSourcePoint } from './multiSeriesModel';

// --------------------------------------------------------------------------- #
// Display transforms
// --------------------------------------------------------------------------- #

export function displaySeries(
  points: readonly MultiSeriesNullableSourcePoint[],
  { scale = 1, cumulative = false }: { scale?: number; cumulative?: boolean } = {},
): MultiSeriesNullableSourcePoint[] {
  let total = 0;
  let complete = true;
  return points.map((point) => {
    if (point.y === null) {
      if (cumulative) complete = false;
      return { ...point, y: null };
    }
    total += point.y;
    return { ...point, y: cumulative ? (complete ? total * scale : null) : point.y * scale };
  });
}
