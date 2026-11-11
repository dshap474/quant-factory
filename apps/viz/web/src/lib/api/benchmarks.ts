/**
 * Benchmarks API — the registered daily close series used as chart overlays.
 *
 * The API registers none by default; installed extensions add them, so callers derive
 * every option and default from `useBenchmarks()` and handle an empty list.
 *
 * USAGE:
 *   const { data: options = [] } = useBenchmarks();
 *   const { data: series } = useBenchmark(options[0]?.ticker ?? '');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export const benchmarkDataSchema = z.object({
  ticker: z.string(),
  data: z.array(
    z.object({
      timestamp: z.string(),
      close: z.number(),
    }),
  ),
  total_rows: z.number(),
});

export type BenchmarkData = z.infer<typeof benchmarkDataSchema>;

export const benchmarkOptionSchema = z.object({
  ticker: z.string(),
  label: z.string(),
  description: z.string(),
});

export type BenchmarkOption = z.infer<typeof benchmarkOptionSchema>;

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function getBenchmarks(signal?: AbortSignal): Promise<BenchmarkOption[]> {
  return getParsed('/api/benchmarks', z.array(benchmarkOptionSchema), { signal });
}

export async function getBenchmark(
  ticker: string,
  startDate?: string,
  endDate?: string,
  signal?: AbortSignal,
): Promise<BenchmarkData> {
  return getParsed('/api/benchmarks/{ticker}', benchmarkDataSchema, {
    params: {
      path: { ticker },
      query: {
        start_date: startDate,
        end_date: endDate,
      },
    },
    signal,
  });
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const benchmarkKeys = {
  all: ['benchmarks'] as const,
  list: () => [...benchmarkKeys.all, 'list'] as const,
  detail: (ticker: string, start?: string, end?: string) =>
    [...benchmarkKeys.all, 'detail', ticker, start ?? null, end ?? null] as const,
};

export function useBenchmark(ticker: string, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: benchmarkKeys.detail(ticker, startDate, endDate),
    queryFn: ({ signal }) => getBenchmark(ticker, startDate, endDate, signal),
    staleTime: STALE.benchmark,
    enabled: Boolean(ticker),
  });
}

/** Registered benchmarks in display order; the first is the default overlay. */
export function useBenchmarks() {
  return useQuery({
    queryKey: benchmarkKeys.list(),
    queryFn: ({ signal }) => getBenchmarks(signal),
    staleTime: STALE.benchmark,
  });
}
