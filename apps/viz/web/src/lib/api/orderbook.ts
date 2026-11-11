/**
 * Validated read-only queries for bounded orderbook charts.
 * USAGE: useOrderbookHeatmap(path, start, bandPercent, hours)
 */

// --------------------------------------------------------------------------- #
// Imports and schemas
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';
import { encodePath } from './paths';

const snapshotSchema = z.object({ timestamp: z.number(), midprice: z.number() });
const heatmapSchema = z.object({
  first: z.number().nullable(),
  last: z.number().nullable(),
  start: z.number().nullable(),
  end: z.number().nullable(),
  snapshots: z.array(snapshotSchema),
  cells: z.array(z.tuple([z.number(), z.number(), z.number(), z.number(), z.number()])),
  price_min: z.number(),
  price_step: z.number(),
  price_bins: z.number(),
  snapshot_count: z.number(),
});
const depthSchema = snapshotSchema.extend({
  levels: z.array(z.object({ price: z.number(), size: z.number(), side: z.enum(['bid', 'ask']) })),
});

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export function useOrderbookHeatmap(
  path: string,
  start: number | null,
  bandPercent: number,
  hours: number,
) {
  return useQuery({
    queryKey: ['orderbook', 'heatmap', path, start, bandPercent, hours],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        band_percent: String(bandPercent),
        hours: String(hours),
      });
      if (start !== null) params.set('start', String(start));
      return requestParsed(
        `/api/catalog/orderbook/heatmap/${encodePath(path)}?${params}`,
        heatmapSchema,
        { signal },
      );
    },
    staleTime: 30_000,
  });
}
export function useOrderbookDepth(
  path: string,
  snapshot: z.infer<typeof snapshotSchema> | undefined,
) {
  return useQuery({
    queryKey: ['orderbook', 'depth', path, snapshot?.timestamp, snapshot?.midprice],
    enabled: Boolean(snapshot),
    queryFn: ({ signal }) => {
      if (!snapshot) throw new Error('Select a snapshot');
      const params = new URLSearchParams({
        timestamp: String(snapshot.timestamp),
        midprice: String(snapshot.midprice),
      });
      return requestParsed(
        `/api/catalog/orderbook/depth/${encodePath(path)}?${params}`,
        depthSchema,
        { signal },
      );
    },
    staleTime: 30_000,
  });
}

// --------------------------------------------------------------------------- #
// Historical calibration, independent of window and visible price range
// --------------------------------------------------------------------------- #

const historicalScaleSchema = z
  .object({
    p50: z.number().finite().nonnegative(),
    p90: z.number().finite().nonnegative(),
    p95: z.number().finite().nonnegative(),
    p99: z.number().finite().nonnegative(),
    price_step: z.number().positive(),
    first: z.number(),
    last: z.number(),
    sample_books: z.number().int().positive(),
    sample_bins: z.number().int().positive(),
    requested_books: z.number().int().positive(),
    partitions: z.number().int().positive(),
    family: z.string(),
    method: z.string(),
  })
  .refine(
    (value) => value.p50 <= value.p90 && value.p90 <= value.p95 && value.p95 <= value.p99,
    'Historical percentiles must be ordered',
  );

export function useOrderbookHistoricalScale(path: string, enabled: boolean) {
  const parts = path.split('/');
  const family = [...parts.slice(0, 4), parts.at(-1)].join('/');
  return useQuery({
    queryKey: ['orderbook', 'historical-scale', family],
    enabled,
    queryFn: ({ signal }) =>
      requestParsed(
        `/api/catalog/orderbook/historical-scale/${encodePath(path)}`,
        historicalScaleSchema,
        { signal },
      ),
    staleTime: 30_000,
  });
}
