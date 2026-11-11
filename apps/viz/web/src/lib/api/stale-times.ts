/**
 * TanStack Query staleTime map for API-backed visualization data.
 *
 * USAGE:
 *   import { STALE } from './stale-times';
 *   useQuery({ staleTime: STALE.list, ... })
 */

// --------------------------------------------------------------------------- #
// Stale times (ms)
// --------------------------------------------------------------------------- #

/** 30s — list pages (strategy types, backtests, signals, …). */
export const STALE_LIST = 30_000;

/** 60s — catalog / docs / feature tree (rarely changes). */
export const STALE_CATALOG = 60_000;

/** 2s — near-realtime surfaces that repoll on a few-second cadence. */
export const STALE_REALTIME = 2_000;

/** 15s — light polling for backfills that grow while a run is in flight. */
export const STALE_POLL = 15_000;

/** 55s — live feeds held just under their 60s refresh interval. */
export const STALE_LIVE_FEED = 55_000;

/** 60s — the refresh interval live feeds poll at. */
export const REFRESH_LIVE_FEED = 60_000;

/** 5min — historical benchmark price data. */
export const STALE_BENCHMARK = 300_000;

/** 5min — generated analysis artifacts (feature analysis, versioned analysis slices). */
export const STALE_ANALYSIS = 300_000;

export const STALE = {
  realtime: STALE_REALTIME,
  poll: STALE_POLL,
  liveFeed: STALE_LIVE_FEED,
  list: STALE_LIST,
  catalog: STALE_CATALOG,
  benchmark: STALE_BENCHMARK,
  analysis: STALE_ANALYSIS,
  /** Detail fetches carry no TTL of their own: always refetch on mount. */
  detail: 0,
} as const;
