/**
 * Portable market observations and time-aligned OHLC / volume rendering layers.
 * USAGE: aggregateMarketBars(minuteBars, 60_000, 300_000); marketCandleSeries(bars).
 */
// --------------------------------------------------------------------------- #
// Imports and contracts
// --------------------------------------------------------------------------- #
import { QF_CHART_RULE_WIDTH } from '../core/geometry';
import { resolveCssColor } from '../theme/tokens';

/** Input bars are located at interval start; rendered observations at interval completion. */
export interface MarketBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface MarketCandle extends MarketBar {
  /** Completion/availability time, never the opening time. */
  availableTime: number;
  duration: number;
}

export interface MarketVolume {
  label: string;
  bars: readonly MarketCandle[];
  color?: string;
}

export interface MarketPriceBand {
  lower: number | null;
  upper: number | null;
}

interface RenderApi {
  value: (dimension: number) => number;
  coord: (point: [number, number]) => [number, number];
}

// --------------------------------------------------------------------------- #
// Complete interval aggregation
// --------------------------------------------------------------------------- #

/** Only contiguous, complete buckets survive; missing minutes never become fabricated candles. */
export function aggregateMarketBars(
  bars: readonly MarketBar[],
  sourceInterval: number,
  interval: number,
): MarketCandle[] {
  if (!(sourceInterval > 0) || interval < sourceInterval || interval % sourceInterval !== 0)
    return [];
  const buckets = new Map<number, MarketBar[]>();
  for (const bar of bars) {
    const start = Math.floor(bar.time / interval) * interval;
    const bucket = buckets.get(start) ?? [];
    bucket.push(bar);
    buckets.set(start, bucket);
  }
  const result: MarketCandle[] = [];
  for (const [time, bucket] of [...buckets].sort(([a], [b]) => a - b)) {
    bucket.sort((a, b) => a.time - b.time);
    if (
      bucket.length !== interval / sourceInterval ||
      bucket.some((bar, index) => bar.time !== time + index * sourceInterval)
    )
      continue;
    const first = bucket[0];
    const last = bucket.at(-1);
    if (!first || !last) continue;
    result.push({
      time,
      availableTime: time + interval,
      duration: interval,
      open: first.open,
      high: Math.max(...bucket.map((bar) => bar.high)),
      low: Math.min(...bucket.map((bar) => bar.low)),
      close: last.close,
      volume: bucket.reduce((sum, bar) => sum + bar.volume, 0),
    });
  }
  return result;
}

/** First completed candle reaching either boundary, including wicks and gaps beyond it.
 * This is a chart endpoint, not an execution price or an inferred order within the candle.
 */
export function firstMarketBandTouch(
  bars: readonly MarketCandle[],
  band: MarketPriceBand,
  window: readonly [number, number],
): number | null {
  let first: number | null = null;
  for (const bar of bars) {
    if (bar.time < window[0] || bar.availableTime > window[1]) continue;
    if (
      (band.lower != null && bar.low <= band.lower) ||
      (band.upper != null && bar.high >= band.upper)
    )
      first = Math.min(first ?? bar.availableTime, bar.availableTime);
  }
  return first;
}

// --------------------------------------------------------------------------- #
// Shared rendering layers
// --------------------------------------------------------------------------- #

export function marketCandleSeries(bars: readonly MarketCandle[]) {
  const upColor = resolveCssColor('var(--qf-chart-candle-up)');
  const downColor = resolveCssColor('var(--qf-chart-candle-down)');
  return {
    id: 'price',
    name: 'OHLC',
    type: 'custom',
    xAxisIndex: 0,
    yAxisIndex: 0,
    clip: true,
    encode: { x: 0, y: [1, 3, 4] },
    data: bars.map((bar) => [
      bar.availableTime,
      bar.close,
      bar.open,
      bar.high,
      bar.low,
      bar.duration,
    ]),
    itemStyle: { color: upColor },
    renderItem: (_params: unknown, api: RenderApi) => {
      const time = api.value(0);
      const close = api.value(1);
      const open = api.value(2);
      const stroke = close >= open ? upColor : downColor;
      const top = api.coord([time, Math.max(open, close)]);
      const bottom = api.coord([time, Math.min(open, close)]);
      const high = api.coord([time, api.value(3)]);
      const low = api.coord([time, api.value(4)]);
      const prior = api.coord([time - api.value(5), close]);
      const width = Math.max(1, Math.min(18, Math.abs(top[0] - prior[0]) * 0.75));
      return {
        type: 'group',
        children: [
          {
            type: 'line',
            shape: { x1: high[0], y1: high[1], x2: low[0], y2: low[1] },
            style: { stroke, lineWidth: QF_CHART_RULE_WIDTH },
          },
          {
            type: 'rect',
            shape: {
              x: top[0] - width / 2,
              y: top[1],
              width,
              height: Math.max(1, bottom[1] - top[1]),
            },
            style: {
              fill: stroke,
              stroke,
              lineWidth: QF_CHART_RULE_WIDTH,
            },
          },
        ],
      };
    },
  };
}

export function marketVolumeSeries(volume: MarketVolume, axisIndex: number, color: string) {
  const fill = resolveCssColor(volume.color ?? color);
  return {
    id: 'volume',
    name: volume.label,
    type: 'custom',
    xAxisIndex: axisIndex,
    yAxisIndex: axisIndex,
    clip: true,
    encode: { x: 0, y: 1 },
    data: volume.bars.map((bar) => [bar.availableTime, bar.volume, bar.duration]),
    itemStyle: { color: fill },
    renderItem: (_params: unknown, api: RenderApi) => {
      const time = api.value(0);
      const top = api.coord([time, api.value(1)]);
      const base = api.coord([time, 0]);
      const prior = api.coord([time - api.value(2), 0]);
      const width = Math.max(1, Math.abs(base[0] - prior[0]) * 0.8);
      return {
        type: 'rect',
        shape: { x: top[0] - width / 2, y: top[1], width, height: Math.max(0, base[1] - top[1]) },
        style: { fill },
      };
    },
  };
}

/** Close observations occur when each supplied bar is complete. */
export function marketClosePoints(
  bars: readonly MarketBar[],
  sourceInterval: number,
): Array<readonly [number, number]> {
  return bars.map((bar) => [bar.time + sourceInterval, bar.close] as const);
}
