/**
 * Raw snapshot recognition and validated per-dataset orderbook view preferences.
 * USAGE: const view = loadOrderbookView(path); saveOrderbookView(path, view);
 */

// --------------------------------------------------------------------------- #
// Contract
// --------------------------------------------------------------------------- #

import { z } from 'zod';

const viewSchema = z.object({
  start: z.number().finite().nonnegative().nullable().default(null),
  hours: z
    .number()
    .int()
    .refine((value) => [1, 3, 6, 24].includes(value))
    .default(6),
  bandPercent: z
    .number()
    .refine((value) => [0, 1, 2, 5].includes(value))
    .default(2),
  scaleMode: z.enum(['relative', 'historical']).default('relative'),
  depthMode: z.enum(['cumulative', 'band']).default('cumulative'),
  selected: z
    .object({
      timestamp: z.number().finite().nonnegative(),
      midprice: z.number().finite().positive(),
    })
    .nullable()
    .default(null),
});
export type OrderbookViewState = z.infer<typeof viewSchema>;

// --------------------------------------------------------------------------- #
// Local preferences
// --------------------------------------------------------------------------- #

function readView(path: string): OrderbookViewState | null {
  try {
    const text = localStorage.getItem(`quant-factory:orderbook:view:${path}`);
    if (!text) return null;
    const result = viewSchema.safeParse(JSON.parse(text));
    return result.success ? result.data : null;
  } catch {
    return null;
  }
}
export function isRawOrderbookPath(path: string): boolean {
  return /^raw\/1m\/[^/]+\/orderbook\/.+_levels\.parquet$/.test(path);
}
export function loadOrderbookView(path: string): OrderbookViewState {
  return readView(path) ?? viewSchema.parse({});
}
export function saveOrderbookView(path: string, view: OrderbookViewState): void {
  try {
    localStorage.setItem(`quant-factory:orderbook:view:${path}`, JSON.stringify(view));
  } catch {
    // Storage can be disabled; the current view still works in memory.
  }
}
