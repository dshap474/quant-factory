/** Screen-spaced crosses along supplied study segments, preserving null/reset gaps.
 * USAGE: crossSeries('level:vwap:solid', 'VWAP', color, points).
 */
// --------------------------------------------------------------------------- #
// Contracts and geometry
// --------------------------------------------------------------------------- #
import type { PriceProfilePoint } from './priceProfileTypes';

const CROSS_SPACING = 8;
const CROSS_RADIUS = 1.5;

export interface CrossRenderApi {
  value: (dimension: number) => number;
  coord: (point: [number, number]) => [number, number];
}

export interface CrossRenderParams {
  coordSys: { x: number; width: number };
}

// --------------------------------------------------------------------------- #
// Rendering layer
// --------------------------------------------------------------------------- #
export function crossSeries(
  id: string,
  name: string,
  color: string,
  points: readonly PriceProfilePoint[],
) {
  return {
    id,
    name,
    type: 'custom',
    xAxisIndex: 0,
    yAxisIndex: 0,
    clip: true,
    silent: true,
    encode: { x: 0, y: 1 },
    itemStyle: { color },
    data: points.map(([time, value], index) => [
      time,
      value,
      points[index - 1]?.[0] ?? time,
      points[index - 1]?.[1] ?? null,
    ]),
    renderItem: ({ coordSys }: CrossRenderParams, api: CrossRenderApi) => {
      const value = api.value(1);
      const priorValue = api.value(3);
      if (!Number.isFinite(value) || !Number.isFinite(priorValue)) return null;
      const [fromX, fromY] = api.coord([api.value(2), priorValue]);
      const [toX, toY] = api.coord([api.value(0), value]);
      if (toX <= fromX) return null;
      // Anchor to plot pixels, recalculated by ECharts on every zoom or resize.
      const origin = coordSys.x + CROSS_SPACING / 2;
      const first =
        origin + Math.max(0, Math.floor((fromX - origin) / CROSS_SPACING) + 1) * CROSS_SPACING;
      const last = Math.min(toX, coordSys.x + coordSys.width - CROSS_RADIUS);
      const children = [];
      for (let x = first; x <= last; x += CROSS_SPACING) {
        const y = fromY + ((x - fromX) / (toX - fromX)) * (toY - fromY);
        children.push(
          {
            type: 'line',
            shape: { x1: x - CROSS_RADIUS, y1: y, x2: x + CROSS_RADIUS, y2: y },
            style: { stroke: color, lineWidth: 1 },
          },
          {
            type: 'line',
            shape: { x1: x, y1: y - CROSS_RADIUS, x2: x, y2: y + CROSS_RADIUS },
            style: { stroke: color, lineWidth: 1 },
          },
        );
      }
      return children.length ? { type: 'group', children } : null;
    },
  };
}
