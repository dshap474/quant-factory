/**
 * Benchmark overlay types for strategy/signal time-series charts.
 *
 * USAGE:
 *   import type { BenchmarkSeriesItem, IndexMode } from '@/lib/shared/lib/benchmark';
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type IndexMode = string | null;

export interface BenchmarkPoint {
  date: Date;
  value: number;
}

export interface BenchmarkSeriesItem {
  ticker: string;
  color: string;
  data: BenchmarkPoint[];
}
