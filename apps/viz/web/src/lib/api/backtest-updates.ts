/**
 * Backtest updates API — each version rerun on the newest inputs beside its published backtest.
 *
 * USAGE:
 *   const { data: versions } = useBacktestUpdateVersions('example');
 *   const { data: view } = useBacktestUpdate('example', 'v002');  // polls while a job runs
 *   const update = useStartBacktestUpdate('example', 'v002');  update.mutate();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed, requestParsed } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

/** Per version, when its backtest ran (`VERSION.toml` `backtest_run_at`) and whether it has a `rerun.py`. */
export const backtestUpdateVersionsSchema = z.record(
  z.string(),
  z.object({ backtest_run_at: z.string().nullable(), updatable: z.boolean() }),
);

const jobSchema = z.object({
  state: z.enum(['running', 'done', 'failed']),
  started_at: z.string(),
  finished_at: z.string().optional(),
  error: z.string().optional(),
});

export const backtestUpdateSchema = z.object({
  family: z.string(),
  version: z.string(),
  updatable: z.boolean(),
  job: jobSchema.nullable(),
  presets: z.array(
    z.object({
      preset: z.string(),
      refreshed_at: z.string(),
      inputs_end: z.string(),
      nav: z.number(),
      series: z.array(z.object({ timestamp: z.string(), nav: z.number() })),
    }),
  ),
});

export type BacktestUpdate = z.infer<typeof backtestUpdateSchema>;

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

const POLL_MS = 10_000;

export const backtestUpdateKeys = {
  all: ['backtest-updates'] as const,
  versions: (family: string) => [...backtestUpdateKeys.all, 'versions', family] as const,
  version: (family: string, version: string) =>
    [...backtestUpdateKeys.all, 'version', family, version] as const,
};

export function useBacktestUpdateVersions(family: string) {
  return useQuery({
    queryKey: backtestUpdateKeys.versions(family),
    queryFn: ({ signal }) =>
      getParsed('/api/backtest-updates/{family}', backtestUpdateVersionsSchema, {
        params: { path: { family } },
        signal,
      }),
    staleTime: STALE.list,
    enabled: Boolean(family),
  });
}

export function useBacktestUpdate(family: string, version: string) {
  return useQuery({
    queryKey: backtestUpdateKeys.version(family, version),
    queryFn: ({ signal }) =>
      getParsed('/api/backtest-updates/{family}/{version}', backtestUpdateSchema, {
        params: { path: { family, version } },
        signal,
      }),
    staleTime: STALE.detail,
    enabled: Boolean(family && version),
    refetchInterval: (query) => (query.state.data?.job?.state === 'running' ? POLL_MS : false),
  });
}

export function useStartBacktestUpdate(family: string, version: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      requestParsed(
        `/api/backtest-updates/${encodeURIComponent(family)}/${encodeURIComponent(version)}`,
        jobSchema,
        { method: 'POST' },
      ),
    onSettled: () =>
      client.invalidateQueries({ queryKey: backtestUpdateKeys.version(family, version) }),
  });
}
