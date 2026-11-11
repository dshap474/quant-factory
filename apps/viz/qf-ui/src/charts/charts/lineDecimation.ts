/**
 * Width-independent thinning for dense line series (M4: first, min, max, last per bucket).
 *
 * ECharts' own `sampling` reduces a series to the grid's pixel width before it computes
 * the value-axis extent, so a resize (collapsing the legend) keeps different extremes and
 * moves every y label. This reduction uses a fixed bucket count instead, keeps each
 * bucket's minimum and maximum (so the extent is exactly the full data's), and keeps a
 * gap marker wherever a bucket holds a gap, so broken lines stay broken.
 *
 * USAGE:
 *   const data = decimateLineData(points.map((p) => [p.date.getTime(), p.value ?? '-']));
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** One ECharts line datum: timestamp and value, or '-' for a gap. */
export type QfLineDatum = [number, number | '-'];

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Series at or below this many points render untouched. */
export const LINE_DECIMATION_THRESHOLD = 4000;
/** Buckets a thinned series is reduced to; each keeps at most four points and a gap. */
const LINE_DECIMATION_BUCKETS = 1000;

// --------------------------------------------------------------------------- #
// Decimation
// --------------------------------------------------------------------------- #

export function decimateLineData(
  data: readonly QfLineDatum[],
  threshold: number = LINE_DECIMATION_THRESHOLD,
): QfLineDatum[] {
  if (data.length <= threshold) return data as QfLineDatum[];
  const bucketSize = Math.ceil(data.length / LINE_DECIMATION_BUCKETS);
  const kept: QfLineDatum[] = [];
  for (let start = 0; start < data.length; start += bucketSize) {
    const end = Math.min(start + bucketSize, data.length);
    let first = -1;
    let last = -1;
    let min = -1;
    let max = -1;
    let gap = -1;
    for (let index = start; index < end; index += 1) {
      const value = data[index]?.[1];
      if (value === '-' || value === undefined || !Number.isFinite(value)) {
        if (gap < 0) gap = index;
        continue;
      }
      if (first < 0) first = index;
      last = index;
      if (min < 0 || value < (data[min]?.[1] as number)) min = index;
      if (max < 0 || value > (data[max]?.[1] as number)) max = index;
    }
    const indices = [...new Set([first, min, max, last, gap])]
      .filter((index) => index >= 0)
      .sort((a, b) => a - b);
    for (const index of indices) {
      const datum = data[index];
      if (datum) kept.push(datum);
    }
  }
  return kept;
}
