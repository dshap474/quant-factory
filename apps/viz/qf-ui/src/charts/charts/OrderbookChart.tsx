/**
 * Portable liquidity heatmap and selected-book depth renderers.
 *
 * USAGE: <OrderbookLiquidityChart data={heatmap} selectedIndex={0} onSelect={select} />
 *        <OrderbookDepthChart levels={levels} midprice={midprice} cumulative />
 */

// --------------------------------------------------------------------------- #
// Imports and contracts
// --------------------------------------------------------------------------- #

import type { CustomSeriesRenderItem } from 'echarts';
import { useMemo } from 'react';
import { ChartState } from '../components/ChartState';
import { QfChart, type QfChartOption } from '../core/QfChart';
import { useChartTheme } from '../hooks/useChartTheme';
import { resolveCssColor } from '../theme/tokens';
import { escapeHtml } from '../utils/escapeHtml';

export interface OrderbookSnapshot {
  timestamp: number;
  midprice: number;
}
export interface OrderbookHeatmapData {
  snapshots: readonly OrderbookSnapshot[];
  cells: readonly (readonly [number, number, number, number?, number?])[];
  price_min: number;
  price_step: number;
  price_bins: number;
}
export type OrderbookScaleMode = 'relative' | 'historical';
export interface OrderbookHistoricalScale {
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  priceStep: number;
}
export interface OrderbookLiquidityChartProps {
  data: OrderbookHeatmapData;
  selectedIndex: number;
  onSelect?: (index: number) => void;
  /** Optional trade-derived candles, with millisecond UTC bucket timestamps. */
  candles?: readonly OrderbookCandle[];
  /** Host-provided asset or instrument name for accessible descriptions. */
  ariaLabel?: string;
  /** Unit label shown in liquidity tooltips; the renderer never infers units. */
  sizeLabel?: string;
  scaleMode?: OrderbookScaleMode;
  historicalScale?: OrderbookHistoricalScale;
}
export interface OrderbookCandle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
export interface OrderbookLevel {
  price: number;
  size: number;
  side: 'bid' | 'ask';
}
export interface OrderbookDepthChartProps {
  levels: readonly OrderbookLevel[];
  midprice: number;
  cumulative: boolean;
}

// --------------------------------------------------------------------------- #
// Formatting
// --------------------------------------------------------------------------- #

function price(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function time(timestamp: number, seconds = false): string {
  return new Date(timestamp * 1000).toISOString().slice(11, seconds ? 19 : 16);
}
function eventValue(event: unknown): number[] {
  if (!event || typeof event !== 'object') return [];
  const value = (event as { value?: unknown }).value;
  return Array.isArray(value)
    ? value.filter((entry): entry is number => typeof entry === 'number')
    : [];
}

// --------------------------------------------------------------------------- #
// Heatmap
// --------------------------------------------------------------------------- #

export function OrderbookLiquidityChart({
  data,
  selectedIndex,
  onSelect,
  candles,
  ariaLabel = 'Orderbook liquidity',
  sizeLabel = 'Size (provider units)',
  scaleMode = 'relative',
  historicalScale,
}: OrderbookLiquidityChartProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const cellDetails = new Map(
      data.cells.map((cell) => [`${cell[0]}:${data.price_min + cell[1] * data.price_step}`, cell]),
    );
    const maximum = Math.max(0, ...data.cells.map((cell) => cell[2])) || 1;
    const gaps = data.snapshots
      .slice(1)
      .map((book, index) => book.timestamp - (data.snapshots[index]?.timestamp ?? book.timestamp))
      .filter((gap) => gap > 0)
      .sort((a, b) => a - b);
    const interval = (gaps[Math.floor(gaps.length / 2)] ?? (candles ? 1 : 60)) * 1000;
    const shortWindow =
      Boolean(candles) &&
      (data.snapshots.at(-1)?.timestamp ?? 0) - (data.snapshots[0]?.timestamp ?? 0) < 120;
    // One slot per second keeps candles and sampled depth on the same clock.
    const firstSecond = Math.floor(
      Math.min(
        data.snapshots[0]?.timestamp ?? Number.POSITIVE_INFINITY,
        (candles?.[0]?.timestamp ?? Number.POSITIVE_INFINITY) / 1000,
      ),
    );
    const lastSecond = Math.floor(
      Math.max(data.snapshots.at(-1)?.timestamp ?? 0, (candles?.at(-1)?.timestamp ?? 0) / 1000),
    );
    const seconds = candles
      ? Array.from({ length: Math.max(0, lastSecond - firstSecond + 1) }, (_, i) => firstSecond + i)
      : [];
    const observed = new Map(
      candles?.map((candle) => [Math.floor(candle.timestamp / 1000), candle]),
    );
    let previousClose: number | undefined;
    const candleValues = seconds.flatMap((second, index) => {
      const candle = observed.get(second);
      if (candle) previousClose = candle.close;
      if (previousClose === undefined) return [];
      return [
        [
          index,
          candle?.open ?? previousClose,
          candle?.close ?? previousClose,
          candle?.low ?? previousClose,
          candle?.high ?? previousClose,
          candle?.volume ?? 0,
          candle ? 1 : 0,
        ],
      ];
    });
    const renderItem: CustomSeriesRenderItem = (_params, api) => {
      const timestamp = Number(api.value(0));
      const level = Number(api.value(1));
      const low = api.coord([candles ? timestamp : timestamp - interval / 2, level]);
      const high = api.coord([
        candles ? timestamp : timestamp + interval / 2,
        level + data.price_step,
      ]);
      const [centerOrLeft, bottom] = low;
      const [centerOrRight, top] = high;
      const slotSize = candles ? api.size?.([1, 0]) : undefined;
      const bandWidth = Array.isArray(slotSize) ? Math.abs(slotSize[0] ?? 0) : 0;
      const left = centerOrLeft === undefined ? undefined : centerOrLeft - bandWidth / 2;
      const right = centerOrRight === undefined ? undefined : centerOrRight + bandWidth / 2;
      if (left === undefined || bottom === undefined || right === undefined || top === undefined)
        return;
      return {
        type: 'rect',
        shape: {
          x: left,
          y: top,
          width: right - left + 0.5,
          height: bottom - top + 0.5,
        },
        style: { fill: api.visual('color') ?? theme.palette[0] ?? theme.axis },
      };
    };
    const midpoint: (number | null)[][] = [];
    data.snapshots.forEach((book, index) => {
      const previous = data.snapshots[index - 1];
      if (previous && (book.timestamp - previous.timestamp) * 1000 > interval * 1.5)
        midpoint.push([previous.timestamp * 1000 + interval, null]);
      midpoint.push([book.timestamp * 1000, book.midprice, index]);
    });
    return {
      animation: false,
      grid: { left: 88, right: 110, top: 24, bottom: 52 },
      xAxis: {
        ...(candles
          ? { type: 'category', data: seconds, boundaryGap: true }
          : {
              type: 'time',
              min: (data.snapshots[0]?.timestamp ?? 0) * 1000 - interval / 2,
              max: (data.snapshots.at(-1)?.timestamp ?? 0) * 1000 + interval / 2,
            }),
        axisLabel: {
          color: theme.axis,
          formatter: (value: number | string) =>
            time(Number(value) / (candles ? 1 : 1000), shortWindow),
          hideOverlap: true,
          ...(candles ? { interval: Math.max(0, Math.ceil(seconds.length / 6) - 1) } : {}),
        },
        axisTick: { show: false },
        axisPointer: {
          show: true,
          label: { show: false },
          lineStyle: { color: theme.crosshair, type: 'dotted' },
        },
        axisLine: { lineStyle: { color: theme.frame } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: data.price_min,
        max: data.price_min + data.price_step * data.price_bins,
        axisLabel: { color: theme.axis, formatter: price },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: theme.grid, opacity: theme.gridOpacity } },
      },
      visualMap:
        scaleMode === 'historical' && historicalScale
          ? {
              type: 'piecewise',
              dimension: 2,
              seriesIndex: 0,
              right: 8,
              top: 'center',
              textStyle: { color: theme.axis },
              itemWidth: 14,
              itemHeight: 14,
              pieces: [
                { gt: historicalScale.p99, label: '> P99', color: theme.palette[0] },
                {
                  gt: historicalScale.p95,
                  lte: historicalScale.p99,
                  label: 'P95–99',
                  color: theme.palette[2],
                },
                {
                  gt: historicalScale.p90,
                  lte: historicalScale.p95,
                  label: 'P90–95',
                  color: resolveCssColor(
                    `color-mix(in srgb, ${theme.palette[2]} 40%, ${theme.background})`,
                  ),
                },
                {
                  gt: historicalScale.p50,
                  lte: historicalScale.p90,
                  label: 'P50–90',
                  color: resolveCssColor(
                    `color-mix(in srgb, ${theme.palette[2]} 15%, ${theme.background})`,
                  ),
                },
                {
                  lte: historicalScale.p50,
                  label: '≤ P50',
                  color: resolveCssColor(
                    `color-mix(in srgb, ${theme.palette[2]} 5%, ${theme.background})`,
                  ),
                },
              ],
              selectedMode: false,
            }
          : {
              type: 'continuous',
              min: 0,
              max: maximum,
              dimension: 2,
              seriesIndex: 0,
              right: 8,
              top: 'center',
              text: ['High size', 'Low size'],
              formatter: (value: number) =>
                value.toLocaleString(undefined, { maximumFractionDigits: 2 }),
              textStyle: { color: theme.axis },
              inRange: {
                color: [
                  theme.background,
                  resolveCssColor(
                    `color-mix(in srgb, ${theme.palette[2]} 15%, ${theme.background})`,
                  ),
                  theme.palette[2],
                  theme.palette[0],
                ],
              },
            },
      tooltip: {
        formatter: (event: unknown) => {
          const value = eventValue(event);
          if (value.length === 7) {
            return (
              `${escapeHtml(time(seconds[value[0] ?? 0] ?? 0, true))} UTC<br/>` +
              `O ${price(value[1] ?? 0)} · H ${price(value[4] ?? 0)} · L ${price(value[3] ?? 0)} · C ${price(value[2] ?? 0)}<br/>` +
              `Volume ${value[5]?.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${escapeHtml(sizeLabel)} · ${value[6] ? 'provisional' : 'no observed trades; last close'}`
            );
          }
          const index = value.length === 3 ? value[2] : value[3];
          const book = index === undefined ? undefined : data.snapshots[index];
          const level = value[1];
          if (!book || level === undefined) return '';
          if (value.length === 3)
            return escapeHtml(
              `${new Date(book.timestamp * 1000)
                .toISOString()
                .slice(0, shortWindow ? 19 : 16)
                .replace('T', ' ')} UTC · Midpoint ${price(level)}`,
            );
          const size = value[2] ?? 0;
          const cell = cellDetails.get(`${index}:${level}`);
          const exactSize = (amount: number) =>
            amount.toLocaleString(undefined, { maximumSignificantDigits: 15 });
          const reference =
            scaleMode === 'historical' && historicalScale
              ? size > historicalScale.p99
                ? '> P99'
                : size > historicalScale.p95
                  ? 'P95–99'
                  : size > historicalScale.p90
                    ? 'P90–95'
                    : size > historicalScale.p50
                      ? 'P50–90'
                      : '≤ P50'
              : `${((100 * size) / maximum).toFixed(1)}% of window maximum`;
          return [
            `<strong>${escapeHtml(
              new Date(book.timestamp * 1000)
                .toISOString()
                .slice(0, shortWindow ? 19 : 16)
                .replace('T', ' '),
            )} UTC</strong>`,
            `Price band: ${price(level)}–${price(level + data.price_step)}`,
            `${escapeHtml(sizeLabel)}: ${exactSize(size)}`,
            ...(cell?.[3] !== undefined && cell[4] !== undefined
              ? [`Bids: ${exactSize(cell[3])} · Asks: ${exactSize(cell[4])}`]
              : []),
            `${scaleMode === 'historical' ? 'Historical band' : 'Relative size'}: ${escapeHtml(reference)}`,
          ].join('<br/>');
        },
      },
      series: [
        {
          name: 'Liquidity',
          type: 'custom',
          renderItem,
          clip: true,
          progressive: 0,
          encode: { x: 0, y: 1 },
          data: data.cells.map(([index, bin, size]) => [
            candles
              ? Math.floor(data.snapshots[index]?.timestamp ?? 0) - firstSecond
              : (data.snapshots[index]?.timestamp ?? 0) * 1000,
            data.price_min + bin * data.price_step,
            size,
            index,
          ]),
        },
        {
          ...(candles
            ? {
                name: '1s candles',
                type: 'candlestick',
                z: 20,
                barWidth: '80%',
                itemStyle: {
                  color: theme.tooltipText,
                  color0: theme.axis,
                  borderColor: theme.tooltipText,
                  borderColor0: theme.tooltipText,
                  borderColorDoji: theme.tooltipText,
                  borderWidth: 1.25,
                },
                emphasis: { disabled: true },
                encode: { x: 0, y: [1, 2, 3, 4] },
                data: candleValues,
              }
            : {
                name: 'Midpoint',
                type: 'line',
                z: 10,
                showSymbol: false,
                lineStyle: { color: theme.palette[0], width: theme.lineWidth },
                data: midpoint,
                markLine: {
                  silent: true,
                  symbol: 'none',
                  label: {
                    formatter: time(data.snapshots[selectedIndex]?.timestamp ?? 0),
                    color: theme.tooltipText,
                    backgroundColor: theme.tooltipBackground,
                    padding: [4, 6],
                    position: 'end',
                    rotate: 0,
                    distance: 6,
                  },
                  lineStyle: { color: theme.axis, type: 'dashed', opacity: 0.7 },
                  data: [{ xAxis: (data.snapshots[selectedIndex]?.timestamp ?? 0) * 1000 }],
                },
              }),
        },
      ],
      aria: { enabled: true },
    };
  }, [data, selectedIndex, sizeLabel, scaleMode, historicalScale, theme, candles]);
  if (
    scaleMode === 'historical' &&
    (!historicalScale || historicalScale.priceStep !== data.price_step)
  ) {
    return (
      <ChartState
        status="error"
        message="Historical scale requires a baseline calibrated with the same price-bin width."
      />
    );
  }
  return (
    <QfChart
      option={option}
      height={candles ? '100%' : undefined}
      ariaLabel={
        candles
          ? `${ariaLabel} heatmap with provisional 1-second candles. ${scaleMode} size scale.`
          : `${ariaLabel} heatmap. ${scaleMode} size scale. Selected ${time(data.snapshots[selectedIndex]?.timestamp ?? 0)} UTC. Click a cell to inspect depth. Left and right arrows select timestamps.`
      }
      interactive={Boolean(onSelect)}
      onClick={(event) => {
        const value = eventValue(event);
        if (value.length === 7) return;
        const index = value.length === 3 ? value[2] : value[3];
        if (index !== undefined && data.snapshots[index]) onSelect?.(index);
      }}
      onKeyDown={(event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        onSelect?.(
          Math.max(
            0,
            Math.min(
              data.snapshots.length - 1,
              selectedIndex + (event.key === 'ArrowLeft' ? -1 : 1),
            ),
          ),
        );
      }}
    />
  );
}

// --------------------------------------------------------------------------- #
// Depth
// --------------------------------------------------------------------------- #

export function OrderbookDepthChart({ levels, midprice, cumulative }: OrderbookDepthChartProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const sorted = [...levels].sort((a, b) => a.price - b.price);
    const values = new Map<number, number>();
    for (const side of ['bid', 'ask'] as const) {
      const rows = sorted.filter((level) => level.side === side);
      if (side === 'bid') rows.reverse();
      let total = 0;
      for (const level of rows) {
        total += level.size;
        values.set(level.price, cumulative ? total : level.size);
      }
    }
    return {
      animation: false,
      grid: { left: 88, right: 110, top: 24, bottom: 60 },
      legend: { orient: 'vertical', right: 8, top: 'center', textStyle: { color: theme.axis } },
      xAxis: {
        type: 'value',
        name: 'Price',
        scale: true,
        axisLabel: { color: theme.axis, formatter: price },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: cumulative ? 'Cumulative size' : 'Band size',
        axisLabel: { color: theme.axis },
        splitLine: { lineStyle: { color: theme.grid } },
      },
      tooltip: {
        trigger: 'item',
        formatter: (event: unknown) => {
          const value = eventValue(event);
          return escapeHtml(
            `Price ${price(value[0] ?? 0)} · ${cumulative ? 'Cumulative size' : 'Band size'} ${price(value[1] ?? 0)}`,
          );
        },
      },
      series: ['bid', 'ask'].map((side, index) => ({
        name: side === 'bid' ? 'Bids' : 'Asks',
        type: 'line',
        step: side === 'bid' ? 'start' : 'end',
        showSymbol: false,
        lineStyle: { color: theme.palette[index], width: theme.lineWidth },
        itemStyle: { color: theme.palette[index] },
        areaStyle: { opacity: 0.18 },
        data: sorted
          .filter((level) => level.side === side)
          .map((level) => [level.price, values.get(level.price)]),
        ...(index === 0
          ? {
              markLine: {
                silent: true,
                symbol: 'none',
                data: [{ xAxis: midprice }],
                label: { formatter: `Mid ${price(midprice)}`, color: theme.axis },
                lineStyle: { color: theme.axis },
              },
            }
          : {}),
      })),
      dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
      aria: { enabled: true },
    };
  }, [levels, midprice, cumulative, theme]);
  return (
    <QfChart
      option={option}
      ariaLabel={`${cumulative ? 'Cumulative' : 'Per-band'} bid and ask depth. Midpoint ${price(midprice)}. ${levels.length} stored levels.`}
    />
  );
}
