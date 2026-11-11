/**
 * Pure display transforms for the execution tape: one time grain per window, trades merged
 * into that grain, sampled depth merged into rectangles, and right-edge label placement.
 *
 * USAGE:
 *   const grain = tapeGrainMs(spanMs);
 *   const bubbles = mergeTrades(trades, grain);
 *   const cells = depthCells(books, grain, endTime);
 */

// --------------------------------------------------------------------------- #
// Contracts: every time is epoch milliseconds
// --------------------------------------------------------------------------- #

export interface ExecutionTapeTrade {
  time: number;
  price: number;
  /** Notional or quantity; bubbles compare trades with each other, so any one unit works. */
  size: number;
  /** The side that crossed the spread. */
  side: 'buy' | 'sell';
}

export interface ExecutionTapeQuote {
  time: number;
  bid: number;
  ask: number;
}

export interface ExecutionTapeBook {
  time: number;
  bids: readonly (readonly [number, number])[];
  asks: readonly (readonly [number, number])[];
}

export interface MergedTrade extends ExecutionTapeTrade {
  count: number;
}

export interface DepthCell {
  start: number;
  end: number;
  low: number;
  high: number;
  /** 1..DEPTH_SHADES; quantized so a level that barely changes stays one rectangle. */
  shade: number;
}

export interface TapeTag {
  value: number;
  y: number;
  text: string;
  color: string;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

export const DEPTH_SHADES = 6;
/** Bubbles and depth columns across the plot, so a long run stays light and readable. */
const TARGET_COLUMNS = 320;
const GRAINS_MS = [50, 100, 250, 500, 1000, 2000, 5000, 10_000, 30_000, 60_000];
const SIZE_QUANTILE = 0.98;

// --------------------------------------------------------------------------- #
// Grain and scale
// --------------------------------------------------------------------------- #

/** Grains come from a fixed ladder, so bubbles do not reshuffle on every update. */
export function tapeGrainMs(spanMs: number): number {
  const wanted = spanMs / TARGET_COLUMNS;
  return GRAINS_MS.find((grain) => grain >= wanted) ?? GRAINS_MS.at(-1) ?? 1000;
}

/** A high quantile rather than the maximum, so one whale does not shrink every other mark. */
export function sizeCeiling(sizes: readonly number[]): number {
  if (!sizes.length) return 1;
  const sorted = [...sizes].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * SIZE_QUANTILE)] || 1;
}

/** Marks are compared by area, so diameter follows the square root of size. */
export function markDiameter(size: number, ceiling: number, min: number, max: number): number {
  return min + (max - min) * Math.sqrt(Math.min(1, Math.max(0, size) / ceiling));
}

// --------------------------------------------------------------------------- #
// Trades
// --------------------------------------------------------------------------- #

/** Trades in one grain at one price on one side are one bubble. */
export function mergeTrades(
  trades: readonly ExecutionTapeTrade[],
  grainMs: number,
): readonly MergedTrade[] {
  const merged = new Map<string, MergedTrade>();
  for (const trade of trades) {
    const key = `${Math.floor(trade.time / grainMs)}:${trade.side}:${trade.price}`;
    const existing = merged.get(key);
    if (existing) {
      existing.size += trade.size;
      existing.count += 1;
    } else {
      merged.set(key, { ...trade, count: 1 });
    }
  }
  return [...merged.values()];
}

// --------------------------------------------------------------------------- #
// Depth
// --------------------------------------------------------------------------- #

/** The smallest gap between neighbouring levels: the height of one price level on screen. */
export function levelStep(books: readonly ExecutionTapeBook[]): number | null {
  let step = Number.POSITIVE_INFINITY;
  for (const book of books) {
    for (const side of [book.bids, book.asks]) {
      for (let index = 1; index < side.length; index += 1) {
        const gap = Math.abs((side[index]?.[0] ?? 0) - (side[index - 1]?.[0] ?? 0));
        if (gap > 0 && gap < step) step = gap;
      }
    }
  }
  return Number.isFinite(step) ? step : null;
}

export function depthCells(
  books: readonly ExecutionTapeBook[],
  grainMs: number,
  endTime: number,
): readonly DepthCell[] {
  const step = levelStep(books);
  if (step === null) return [];
  const columns = new Map<number, ExecutionTapeBook>();
  for (const book of books) columns.set(Math.floor(book.time / grainMs), book);
  const sampled = [...columns.values()];
  const ceiling = sizeCeiling(sampled.flatMap((book) => [...book.bids, ...book.asks].map(sizeOf)));
  const cells: DepthCell[] = [];
  let open = new Map<number, DepthCell>();
  sampled.forEach((book, index) => {
    const end = sampled[index + 1]?.time ?? endTime;
    const next = new Map<number, DepthCell>();
    for (const [price, size] of [...book.bids, ...book.asks]) {
      const shade = Math.max(1, Math.round(Math.sqrt(Math.min(1, size / ceiling)) * DEPTH_SHADES));
      const running = open.get(price);
      if (running?.shade === shade) {
        running.end = end;
        next.set(price, running);
      } else {
        const cell = {
          start: book.time,
          end,
          low: price - step / 2,
          high: price + step / 2,
          shade,
        };
        cells.push(cell);
        next.set(price, cell);
      }
    }
    open = next;
  });
  return cells;
}

function sizeOf(level: readonly [number, number]): number {
  return level[1];
}

// --------------------------------------------------------------------------- #
// Right-edge tags
// --------------------------------------------------------------------------- #

/** Spread labels apart top-down so close prices stay legible, then keep them inside the plot. */
export function placeTags(
  tags: readonly TapeTag[],
  gap: number,
  top: number,
  bottom: number,
): readonly TapeTag[] {
  const placed = [...tags].sort((a, b) => a.y - b.y).map((tag) => ({ ...tag }));
  placed.forEach((tag, index) => {
    const previous = placed[index - 1];
    tag.y = Math.max(previous ? previous.y + gap : top, tag.y);
  });
  for (let index = placed.length - 1; index >= 0; index -= 1) {
    const tag = placed[index];
    if (!tag) continue;
    const below = placed[index + 1];
    tag.y = Math.min(below ? below.y - gap : bottom, tag.y);
  }
  return placed;
}
