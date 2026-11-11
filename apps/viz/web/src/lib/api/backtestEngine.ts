/**
 * Backtest Engine API — saved strategy runs, their telemetry, Update-backtest jobs, one run's
 * replay (equity, positions, rebalances), and, for runs whose family serves them, one held
 * asset over the run (price, weight, position P&L, rebalances) and one rebalance day worked
 * intraday under each execution policy. Read-only; polls fast while anything runs.
 *
 * USAGE:
 *   const runs = useBacktestEngineRuns({ families: [], states: ['failed'] });  // newest first
 *   const run = useBacktestEngineRun({ family, version, preset, runId });
 *   const btc = useBacktestAsset({ family, version, preset, runId }, 'BTC');
 *   const day = useBacktestExecutionDay({ family, version, preset, runId }, '2024-01-02');
 *   executionDayHref(run, '2024-01-02')   // '<runHref>/execution/2024-01-02'
 *   runHref(run)   // '/backtest-engine/runs/<family>/<version>/<preset>/<run_id>'
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed } from './client';
import { ApiError } from './errors';

// --------------------------------------------------------------------------- #
// Schemas and types
// --------------------------------------------------------------------------- #

const numberList = z.array(z.number().nullable());

export const backtestRunSchema = z.object({
  family: z.string(),
  version: z.string(),
  preset: z.string(),
  run_id: z.string(),
  state: z.enum(['running', 'succeeded', 'failed']),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  duration_s: z.number().nullable(),
  phases: z.record(z.string(), z.number()),
  engine: z.string().nullable(),
  rows: z.number().nullable(),
  assets: z.number().nullable(),
  host: z.string().nullable(),
  pid: z.number().nullable(),
  error: z.string().nullable(),
  lag_bars: z.number().nullable(),
  metrics: z.record(z.string(), z.number()),
  data_range: z.record(z.string(), z.string()).nullable(),
});

const updateJobSchema = z.object({
  family: z.string(),
  version: z.string(),
  state: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error: z.string().nullable(),
});

export const backtestRunListSchema = z.object({
  runs: z.array(backtestRunSchema),
  updates: z.array(updateJobSchema),
  summary: z.object({
    running: z.number(),
    failed_24h: z.number(),
    runs_7d: z.number(),
    last_finished_at: z.string().nullable(),
  }),
  families: z.array(z.string()),
});

export const backtestReplaySchema = z.object({
  rows: z.number(),
  weights_known: z.boolean(),
  equity: z.object({
    timestamp: z.array(z.string()),
    equity: numberList,
    benchmark_equity: numberList,
    drawdown: numberList,
    return_to_date: numberList,
    gross_exposure: numberList,
    net_exposure: numberList,
  }),
  positions: z.object({
    assets: z.array(z.string()),
    weights: z.record(z.string(), numberList),
  }),
  trades: z.array(
    z.object({
      timestamp: z.string(),
      asset: z.string(),
      from_weight: z.number(),
      to_weight: z.number(),
      delta: z.number(),
    }),
  ),
  total_trades: z.number(),
  held_assets: z.array(z.string()),
});

export const backtestRunDetailSchema = z.object({
  status: backtestRunSchema,
  meta: z.record(z.string(), z.unknown()).nullable(),
  replay: backtestReplaySchema.nullable(),
  execution: z.boolean(),
  assets: z.boolean(),
});

export const backtestAssetSchema = z.object({
  asset: z.string(),
  timestamp: z.array(z.string()),
  price: numberList,
  weight: numberList,
  pnl: numberList,
  trades: z.array(
    z.object({ timestamp: z.string(), delta: z.number(), price: z.number().nullable() }),
  ),
});

const nullableNumber = z.number().nullable();

export const executionDaySchema = z.object({
  decision_at: z.string(),
  venue: z.string(),
  assumptions: z.record(z.string(), z.number()),
  policies: z.array(z.object({ name: z.string(), horizon_minutes: z.number() })),
  book_times: z.array(z.string()),
  book: z.record(
    z.string(),
    z.object({
      to_buy: z.array(z.number()),
      to_sell: z.array(z.number()),
      cost: z.array(z.number()),
    }),
  ),
  summary: z.array(
    z.object({
      policy: z.string(),
      below_minimum: z.number(),
      filled_share: nullableNumber,
      maker_share: nullableNumber,
      minutes_to_complete: nullableNumber,
      total_bps: nullableNumber,
      fee_bps: nullableNumber,
      spread_bps: nullableNumber,
      drift_bps: nullableNumber,
      unfilled_bps: nullableNumber,
      markouts_bps: z.record(z.string(), nullableNumber),
    }),
  ),
  orders: z.array(
    z.object({
      asset: z.string(),
      side: z.number(),
      notional: z.number(),
      arrival_mid: nullableNumber,
      cost_bps: z.record(z.string(), nullableNumber),
    }),
  ),
  skipped: z.array(z.string()),
});

export const executionAssetSchema = z.object({
  start_ms: z.number(),
  close: numberList,
  volume: numberList,
  fills: z.record(
    z.string(),
    z.object({
      time_ms: z.array(z.number()),
      quantity: z.array(z.number()),
      price: z.array(z.number()),
      maker: z.array(z.boolean()),
      avg_price: z.array(z.number()),
    }),
  ),
});

export type BacktestRun = z.infer<typeof backtestRunSchema>;
export type BacktestUpdateJob = z.infer<typeof updateJobSchema>;
export type BacktestRunList = z.infer<typeof backtestRunListSchema>;
export type BacktestReplay = z.infer<typeof backtestReplaySchema>;
export type BacktestRunDetail = z.infer<typeof backtestRunDetailSchema>;
export type BacktestAsset = z.infer<typeof backtestAssetSchema>;
export type ExecutionDay = z.infer<typeof executionDaySchema>;
export type ExecutionAsset = z.infer<typeof executionAssetSchema>;

export type BacktestRunState = BacktestRun['state'];

/** Server-side filters (the list is a bounded newest-first page); empty selects everything. */
export interface BacktestRunFilters {
  families: string[];
  states: BacktestRunState[];
}

export interface BacktestRunKey {
  family: string;
  version: string;
  preset: string;
  runId: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ACTIVE_POLL_MS = 5_000;
const IDLE_POLL_MS = 30_000;

export function runHref(run: Pick<BacktestRun, 'family' | 'version' | 'preset' | 'run_id'>) {
  return `/backtest-engine/runs/${[run.family, run.version, run.preset, run.run_id]
    .map(encodeURIComponent)
    .join('/')}`;
}

export function executionDayHref(
  run: Pick<BacktestRun, 'family' | 'version' | 'preset' | 'run_id'>,
  day: string,
) {
  return `${runHref(run)}/execution/${encodeURIComponent(day)}`;
}

/** Gateway statuses while the API restarts (a deploy takes a few seconds). */
const UNAVAILABLE = new Set([502, 503, 504]);

/** Retry only while the API is briefly unreachable, ~15 s in all with the default backoff. */
function retryUnavailable(count: number, error: Error) {
  return count < 4 && error instanceof ApiError && UNAVAILABLE.has(error.status);
}

function listPoll(data: BacktestRunList | undefined): number {
  // The summary is store-wide, so a filter hiding the live run never slows polling.
  const live =
    Boolean(data?.summary.running) || data?.updates.some((job) => job.state === 'running');
  return live ? ACTIVE_POLL_MS : IDLE_POLL_MS;
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const backtestEngineKeys = {
  all: ['backtest-engine'] as const,
  runs: (filters: BacktestRunFilters) =>
    [...backtestEngineKeys.all, 'runs', filters.families, filters.states] as const,
  run: (key: BacktestRunKey) =>
    [...backtestEngineKeys.all, 'run', key.family, key.version, key.preset, key.runId] as const,
  asset: (key: BacktestRunKey, asset: string) =>
    [...backtestEngineKeys.run(key), 'asset', asset] as const,
  executionDay: (key: BacktestRunKey, day: string) =>
    [...backtestEngineKeys.run(key), 'execution', day] as const,
  executionAsset: (key: BacktestRunKey, day: string, asset: string) =>
    [...backtestEngineKeys.executionDay(key, day), asset] as const,
};

export function useBacktestEngineRuns(filters: BacktestRunFilters) {
  return useQuery({
    queryKey: backtestEngineKeys.runs(filters),
    queryFn: ({ signal }) =>
      getParsed('/api/backtest-engine/runs', backtestRunListSchema, {
        params: {
          query: {
            limit: 200,
            ...(filters.families.length ? { family: filters.families } : {}),
            ...(filters.states.length ? { state: filters.states } : {}),
          },
        },
        signal,
      }),
    refetchInterval: (query) => listPoll(query.state.data),
    refetchOnWindowFocus: true,
  });
}

export function useBacktestEngineRun(key: BacktestRunKey) {
  return useQuery({
    queryKey: backtestEngineKeys.run(key),
    queryFn: ({ signal }) =>
      getParsed(
        '/api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}',
        backtestRunDetailSchema,
        {
          params: {
            path: {
              family: key.family,
              version: key.version,
              preset: key.preset,
              run_id: key.runId,
            },
          },
          signal,
        },
      ),
    refetchInterval: (query) =>
      query.state.data?.status.state === 'running' ? ACTIVE_POLL_MS : false,
    retry: retryUnavailable,
  });
}

/** One held asset over a finished run; immutable, so it never refetches. */
export function useBacktestAsset(key: BacktestRunKey, asset: string | null) {
  return useQuery({
    queryKey: backtestEngineKeys.asset(key, asset ?? ''),
    queryFn: ({ signal }) =>
      getParsed(
        '/api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/assets/{asset}',
        backtestAssetSchema,
        {
          params: {
            path: {
              family: key.family,
              version: key.version,
              preset: key.preset,
              run_id: key.runId,
              asset: asset ?? '',
            },
          },
          signal,
        },
      ),
    enabled: asset !== null,
    staleTime: Number.POSITIVE_INFINITY,
    retry: retryUnavailable,
  });
}

/** One rebalance day simulated intraday; computed on demand and immutable, so it never refetches. */
export function useBacktestExecutionDay(key: BacktestRunKey, day: string) {
  return useQuery({
    queryKey: backtestEngineKeys.executionDay(key, day),
    queryFn: ({ signal }) =>
      getParsed(
        '/api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/execution/{day}',
        executionDaySchema,
        {
          params: {
            path: {
              family: key.family,
              version: key.version,
              preset: key.preset,
              run_id: key.runId,
              day,
            },
          },
          signal,
        },
      ),
    staleTime: Number.POSITIVE_INFINITY,
    retry: retryUnavailable,
  });
}

/** One traded asset's minute data and fills on a rebalance day; immutable, so it never refetches. */
export function useBacktestExecutionAsset(key: BacktestRunKey, day: string, asset: string | null) {
  return useQuery({
    queryKey: backtestEngineKeys.executionAsset(key, day, asset ?? ''),
    queryFn: ({ signal }) =>
      getParsed(
        '/api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/execution/{day}/assets/{asset}',
        executionAssetSchema,
        {
          params: {
            path: {
              family: key.family,
              version: key.version,
              preset: key.preset,
              run_id: key.runId,
              day,
              asset: asset ?? '',
            },
          },
          signal,
        },
      ),
    enabled: asset !== null,
    staleTime: Number.POSITIVE_INFINITY,
    retry: retryUnavailable,
  });
}
