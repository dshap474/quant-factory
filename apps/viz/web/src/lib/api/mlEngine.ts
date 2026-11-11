/**
 * Read-only ML Engine run API, runtime schemas, and polling hooks.
 *
 * USAGE:
 *   const runsQuery = useMlEngineRuns({ producer: 'family', status: 'running' });
 *   const detailQuery = useMlEngineRun(selectedRunId);
 *   const producersQuery = useMlEngineProducers();
 *
 * The run listing is a bounded newest-first page, so filters must be applied by
 * the API rather than over the fetched window.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed } from './client';

// --------------------------------------------------------------------------- #
// Schemas and types
// --------------------------------------------------------------------------- #

export const ML_ENGINE_ACTIVE_POLL_MS = 2_000;
export const ML_ENGINE_IDLE_POLL_MS = 30_000;
export const ML_ENGINE_STAGES = [
  'validation',
  'planning',
  'cross_validation',
  'evaluation',
  'selection',
  'ensemble',
  'final_refit',
  'artifact_save',
] as const;

const runStatusSchema = z.enum(['running', 'completed', 'failed']);
const runStageSchema = z.enum(ML_ENGINE_STAGES);

const runErrorSchema = z
  .object({
    type: z.string(),
    message: z.string(),
  })
  .strict();

export const mlEngineRunSchema = z
  .object({
    schema_version: z.literal(1),
    run_id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/),
    producer: z.string(),
    status: runStatusSchema,
    operation: z.string(),
    stage: runStageSchema,
    task: z.string().nullable(),
    target: z.string().nullable(),
    feature_count: z.number().int().nonnegative().nullable(),
    final_refit: z.boolean().nullable(),
    candidate: z.string().nullable(),
    candidate_index: z.number().int().positive().nullable(),
    candidate_count: z.number().int().positive().nullable(),
    fold_index: z.number().int().positive().nullable(),
    fold_count: z.number().int().positive().nullable(),
    completed_fits: z.number().int().nonnegative(),
    total_fits: z.number().int().nonnegative().nullable(),
    started_at: z.string(),
    updated_at: z.string(),
    completed_at: z.string().nullable(),
    host: z.string(),
    inference_ready: z.boolean(),
    error: runErrorSchema.nullable(),
  })
  .strict();

export const mlEngineRunListSchema = z
  .object({
    runs: z.array(mlEngineRunSchema),
    count: z.number().int().nonnegative(),
    invalid_count: z.number().int().nonnegative(),
  })
  .strict();

const jsonObjectSchema = z.record(z.string(), z.unknown());

export const mlEngineArtifactSchema = z
  .object({
    path: z.string(),
    manifest: jsonObjectSchema.nullable(),
    config: jsonObjectSchema.nullable(),
    schema: jsonObjectSchema.nullable(),
    metrics: jsonObjectSchema.nullable(),
    selection: jsonObjectSchema.nullable(),
  })
  .strict();

export const mlEngineRunDetailSchema = z
  .object({
    run: mlEngineRunSchema,
    artifact: mlEngineArtifactSchema.nullable(),
  })
  .strict();

export const mlEngineProducerListSchema = z
  .object({
    producers: z.array(z.string()),
    invalid_count: z.number().int().nonnegative(),
  })
  .strict();

export type MlEngineRunStatus = z.infer<typeof runStatusSchema>;
export type MlEngineRun = z.infer<typeof mlEngineRunSchema>;
export type MlEngineRunList = z.infer<typeof mlEngineRunListSchema>;
export type MlEngineRunDetail = z.infer<typeof mlEngineRunDetailSchema>;
export type MlEngineProducerList = z.infer<typeof mlEngineProducerListSchema>;

/** Server-side run filters; omitted fields select every run. */
export interface MlEngineRunQuery {
  producer?: string;
  status?: MlEngineRunStatus;
}

// --------------------------------------------------------------------------- #
// Fetch and polling
// --------------------------------------------------------------------------- #

export async function listMlEngineRuns(
  query: MlEngineRunQuery = {},
  signal?: AbortSignal,
): Promise<MlEngineRunList> {
  return getParsed('/api/ml-engine/runs', mlEngineRunListSchema, {
    params: { query: { producer: query.producer, status: query.status } },
    signal,
  });
}

export async function listMlEngineProducers(signal?: AbortSignal): Promise<MlEngineProducerList> {
  return getParsed('/api/ml-engine/producers', mlEngineProducerListSchema, { signal });
}

export async function getMlEngineRun(
  runId: string,
  signal?: AbortSignal,
): Promise<MlEngineRunDetail> {
  return getParsed('/api/ml-engine/runs/{run_id}', mlEngineRunDetailSchema, {
    params: { path: { run_id: runId } },
    signal,
  });
}

// Abandoned processes leave sidecars stuck at "running" forever; treat a run
// with no update for this long as stale so one zombie cannot pin fast polling.
export const ML_ENGINE_STALE_RUNNING_MS = 10 * 60 * 1_000;

export function isActivelyRunning(run: MlEngineRun, now = Date.now()): boolean {
  return run.status === 'running' && now - Date.parse(run.updated_at) < ML_ENGINE_STALE_RUNNING_MS;
}

export function runListPollInterval(data: MlEngineRunList | undefined): number {
  return data?.runs.some((run) => isActivelyRunning(run))
    ? ML_ENGINE_ACTIVE_POLL_MS
    : ML_ENGINE_IDLE_POLL_MS;
}

export function runDetailPollInterval(data: MlEngineRunDetail | undefined): number {
  return data !== undefined && isActivelyRunning(data.run)
    ? ML_ENGINE_ACTIVE_POLL_MS
    : ML_ENGINE_IDLE_POLL_MS;
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const mlEngineKeys = {
  all: ['ml-engine'] as const,
  list: (query: MlEngineRunQuery = {}) =>
    [...mlEngineKeys.all, 'runs', query.producer ?? null, query.status ?? null] as const,
  producers: () => [...mlEngineKeys.all, 'producers'] as const,
  detail: (runId: string) => [...mlEngineKeys.all, 'run', runId] as const,
};

export function useMlEngineRuns(query: MlEngineRunQuery = {}) {
  return useQuery({
    queryKey: mlEngineKeys.list(query),
    queryFn: ({ signal }) => listMlEngineRuns(query, signal),
    refetchInterval: (result) => runListPollInterval(result.state.data),
    refetchOnWindowFocus: true,
  });
}

// Producer aggregation scans the whole store, so poll it on focus and staleness
// rather than on the run list's live cadence.
export function useMlEngineProducers() {
  return useQuery({
    queryKey: mlEngineKeys.producers(),
    queryFn: ({ signal }) => listMlEngineProducers(signal),
    staleTime: ML_ENGINE_IDLE_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useMlEngineRun(runId: string | null) {
  return useQuery({
    queryKey: mlEngineKeys.detail(runId ?? ''),
    queryFn: ({ signal }) => getMlEngineRun(runId ?? '', signal),
    enabled: runId !== null,
    refetchInterval: (query) => runDetailPollInterval(query.state.data),
    refetchOnWindowFocus: true,
  });
}
