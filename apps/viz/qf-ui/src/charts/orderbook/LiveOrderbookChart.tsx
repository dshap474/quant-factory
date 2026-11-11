/**
 * Portable sampled depth heatmap with provisional one-second candles.
 * USAGE: <LiveOrderbookChart books={books} candles={candles} title="BTC/USD" />
 */

// --------------------------------------------------------------------------- #
// Imports and public millisecond-timestamp contracts
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';
import {
  type OrderbookCandle,
  type OrderbookHeatmapData,
  OrderbookLiquidityChart,
} from '../charts/OrderbookChart';
import { ChartNote } from '../components/ChartNote';
import { ChartState } from '../components/ChartState';
import { TimeSeriesChart } from '../components/TimeSeriesChart';

export interface LiveOrderbookFrame {
  timestamp: number;
  bids: readonly (readonly [number, number])[];
  asks: readonly (readonly [number, number])[];
}
export interface LiveOrderbookChartProps {
  title: string;
  books: readonly LiveOrderbookFrame[];
  candles: readonly OrderbookCandle[];
  sizeLabel: string;
  loading?: boolean;
  error?: string | null;
  stale?: boolean;
}

// --------------------------------------------------------------------------- #
// Price-band aggregation retains each book's identity and both sides
// --------------------------------------------------------------------------- #

export function LiveOrderbookChart({
  title,
  books,
  candles,
  sizeLabel,
  loading = false,
  error,
  stale = false,
}: LiveOrderbookChartProps) {
  const heatmap = useMemo<OrderbookHeatmapData | null>(() => {
    const prices = books.flatMap((book) => [...book.bids, ...book.asks].map((level) => level[0]));
    prices.push(...candles.flatMap((candle) => [candle.low, candle.high]));
    if (!prices.length || !books.length) return null;
    const low = Math.min(...prices);
    const high = Math.max(...prices);
    const rawStep = (high - low || Math.abs(low) * 0.001 || 1) / 80;
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    const step = Math.ceil(rawStep / magnitude) * magnitude;
    const minimum = Math.floor(low / step) * step - step;
    const cells: Array<[number, number, number, number, number]> = [];
    books.forEach((book, index) => {
      const bands = new Map<number, [number, number]>();
      for (const [side, levels] of [
        [0, book.bids],
        [1, book.asks],
      ] as const) {
        for (const [price, size] of levels) {
          const bin = Math.floor((price - minimum) / step);
          const band = bands.get(bin) ?? [0, 0];
          band[side] += size;
          bands.set(bin, band);
        }
      }
      for (const [bin, [bid, ask]] of bands) cells.push([index, bin, bid + ask, bid, ask]);
    });
    return {
      snapshots: books.map((book) => ({
        timestamp: book.timestamp / 1000,
        midprice: ((book.bids[0]?.[0] ?? low) + (book.asks[0]?.[0] ?? high)) / 2,
      })),
      cells,
      price_min: minimum,
      price_step: step,
      price_bins: Math.ceil((high - minimum) / step) + 1,
    };
  }, [books, candles]);
  const latestBook = books.at(-1);
  return (
    <TimeSeriesChart
      title={title}
      headerRight={
        <ChartNote>
          {error
            ? 'Source unavailable'
            : !heatmap
              ? loading
                ? 'Connecting'
                : 'Stopped'
              : stale
                ? 'Snapshot stale'
                : 'Live · UTC · 60s in memory'}
        </ChartNote>
      }
      footer={
        heatmap
          ? `${books.length} sampled books · ${latestBook?.bids.length ?? 0} bid / ${latestBook?.asks.length ?? 0} ask levels · ${heatmap.price_step.toLocaleString(undefined, { maximumFractionDigits: 8 })} price units/band · intensity = ${sizeLabel} · provisional 1s candles`
          : undefined
      }
    >
      {heatmap ? (
        <OrderbookLiquidityChart
          data={heatmap}
          candles={candles}
          selectedIndex={books.length - 1}
          sizeLabel={sizeLabel}
          ariaLabel={title}
        />
      ) : (
        <ChartState
          status={error ? 'error' : loading ? 'loading' : 'empty'}
          message={
            error ??
            (loading
              ? 'Connecting to live market'
              : 'Start the stream to view candles and liquidity.')
          }
        />
      )}
    </TimeSeriesChart>
  );
}
