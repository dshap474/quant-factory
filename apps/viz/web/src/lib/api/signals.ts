/**
 * Signals API — signal predictions and stats.
 *
 * USAGE:
 *   const { data } = useSignals();
 *   const { data: runs } = useSignalRuns(signalId);
 *   const { data: families } = useSignalResearchFamilies();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed, openapiGet } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export const signalSummarySchema = z.object({
  signal_id: z.string(),
  description: z.string(),
  production_version: z.string().nullable().default(null),
  run_count: z.number(),
  best_accuracy: z.number().nullable(),
  best_auc: z.number().nullable(),
  latest_run: z.string().nullable(),
  latest_run_id: z.string().nullable(),
  // The prediction clock, spanning every run. `latest_run` is when the runner fired.
  first_prediction: z.string().nullable(),
  latest_prediction: z.string().nullable(),
});

export const signalResearchFamilySchema = z.object({
  signal_family: z.string(),
  description: z.string(),
  total_runs: z.number().int().nonnegative(),
  version_count: z.number().int().nonnegative(),
  versions: z.array(z.string()),
  latest_run: z.string().nullable(),
});

export const signalResearchVersionSchema = z.object({
  signal_family: z.string(),
  memory_version: z.string(),
  total_runs: z.number().int().nonnegative(),
  run_count: z.number().int().nonnegative(),
  latest_run: z.string().nullable(),
  state: z.enum(['candidate', 'invalidated', 'promoted']),
  display_state: z.enum(['baseline', 'candidate', 'invalidated']),
  source: z.enum(['canonical', 'research']),
  selected_run_id: z.string().nullable(),
  experiment: z.string().nullable(),
  has_surface: z.boolean(),
  // Lifecycle of the published surface, when one is selected for the version.
  surface_state: z.enum(['candidate', 'rejected', 'not_tested']).nullable().default(null),
  lifecycle_phase: z.string().nullable(),
  lifecycle_status: z.string().nullable(),
  invalidation_reason: z.string().nullable(),
  // Canonical versions only: the persisted signal ids (one per preset) this engine version
  // aggregates, and the id that owns `selected_run_id`. Research versions carry none.
  signal_ids: z.array(z.string()).default([]),
  selected_signal_id: z.string().nullable().default(null),
});

const signalMetadataSchema = z
  .object({
    data_start: z.string(),
    data_end: z.string(),
    n_samples: z.number(),
    n_features: z.number(),
    feature_list: z.array(z.string()),
    target: z.string(),
    model_type: z.string(),
    model_params: z.record(z.string(), z.unknown()),
    cv_metrics: z.record(z.string(), z.number()).nullable(),
  })
  .nullable();

export const signalRunSchema = z.object({
  run_id: z.string(),
  metrics: z.record(z.string(), z.number().nullable()).catch({}),
  config: z.record(z.string(), z.unknown()),
  created_at: z.string().nullable(),
  data_range: z.object({ start: z.string(), end: z.string() }).nullable(),
  metadata: signalMetadataSchema,
  // Run listings carry the prediction span; the run payload endpoints do not, hence the
  // default rather than a bare nullable — `signalDataSchema` extends this object.
  first_prediction: z.string().nullable().default(null),
  latest_prediction: z.string().nullable().default(null),
});

export const signalDataSchema = signalRunSchema.extend({
  signal_id: z.string(),
  date_column: z.string().nullable(),
  prediction_columns: z.array(z.string()),
  columns: z.array(z.string()),
  data: z.array(z.record(z.string(), z.unknown())),
  // Multi-asset runs only. `assets` lists the run's whole cross-section; `asset` names the
  // one this payload was narrowed to; `cross_section` marks a payload that is the latest
  // timestamp across assets rather than a history. Optional so single-asset payloads and
  // older API builds still parse.
  assets: z.array(z.string()).nullable().default(null),
  asset: z.string().nullable().default(null),
  cross_section: z.boolean().default(false),
});

export const signalStatsSchema = z.object({
  signal_id: z.string(),
  run_id: z.string(),
  metrics: z.record(z.string(), z.number().nullable()).catch({}),
  metadata: signalMetadataSchema,
  prediction_stats: z.array(
    z.object({
      column: z.string(),
      count: z.number(),
      null_count: z.number(),
      mean: z.number().nullable(),
      std: z.number().nullable(),
      min: z.number().nullable(),
      max: z.number().nullable(),
    }),
  ),
});

/**
 * Envelope for one parquet artifact of a sealed research attempt. The API serves only
 * files listed in the run manifest.
 */
export const signalResearchArtifactTableSchema = z.object({
  signal_family: z.string(),
  memory_version: z.string(),
  experiment: z.string(),
  run_id: z.string(),
  name: z.string(),
  total_rows: z.number().int().nonnegative(),
  returned_rows: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
});

const surfaceTableRefSchema = z.object({ path: z.string(), row_count: z.number().int() });

/** One evaluated arm of a published signal research surface. */
export const signalSurfaceArmSchema = z.object({
  arm_id: z.string(),
  label: z.string(),
  role: z.enum(['control', 'candidate']),
  description: z.string(),
  targets: z.array(z.string()),
  // Null when this run did not produce the table (e.g. single-asset summary-only validations).
  ic: surfaceTableRefSchema.nullable(),
  quantiles: surfaceTableRefSchema.nullable(),
  metrics: z.object({
    path: z.string(),
    values: z.record(z.string(), z.number().nullable()),
  }),
});

/** The selected research surface for one signal version (see signals.research_surface). */
export const signalResearchSurfaceSchema = z
  .object({
    signal_family: z.string(),
    memory_version: z.string(),
    state: z.enum(['candidate', 'rejected', 'not_tested']),
    experiment: z.string(),
    run_id: z.string(),
    published_at: z.string(),
    title: z.string(),
    summary: z.string(),
    headline: z.record(z.string(), z.unknown()).nullable(),
    // Why a not_tested run stopped; null for candidate and rejected surfaces.
    blocker: z.string().nullable().default(null),
    // The target the run's gates were judged on; the view opens on it. Null = first target.
    primary_target: z.string().nullable().default(null),
    // Empty only for a not_tested surface.
    arms: z.array(signalSurfaceArmSchema),
    gates: z.array(
      z
        .object({
          name: z.string(),
          passed: z.boolean(),
          stage: z.string().optional(),
          statistic: z.string().optional(),
          comparison: z.string().optional(),
          threshold: z.number().nullable().optional(),
          value: z.number().nullable().optional(),
        })
        .passthrough(),
    ),
    disclosures: z.array(z.string()),
    provenance: z.array(z.object({ label: z.string(), value: z.string() })),
  })
  .refine((surface) => (surface.state === 'not_tested') === (surface.arms.length === 0), {
    message: 'A not_tested surface has no arms; candidate and rejected surfaces have at least one',
  });

export const signalSurfaceIcRowSchema = z.object({
  decision_time: z.string(),
  target_id: z.string(),
  ic: z.number().nullable(),
  cumulative_ic: z.number(),
});

export const signalSurfaceQuantileRowSchema = z.object({
  target_id: z.string(),
  quantile: z.number().int(),
  label: z.string(),
  mean_target: z.number().nullable(),
  n: z.number().int(),
});

const surfaceTableEnvelope = <T extends z.ZodTypeAny>(row: T) =>
  z.object({
    signal_family: z.string(),
    memory_version: z.string(),
    arm_id: z.string(),
    table: z.enum(['ic', 'quantiles']),
    columns: z.array(z.string()),
    rows: z.array(row),
  });

export const signalSurfaceIcTableSchema = surfaceTableEnvelope(signalSurfaceIcRowSchema);
export const signalSurfaceQuantileTableSchema = surfaceTableEnvelope(
  signalSurfaceQuantileRowSchema,
);

export type SignalSummary = z.infer<typeof signalSummarySchema>;
export type SignalResearchFamily = z.infer<typeof signalResearchFamilySchema>;
export type SignalResearchVersion = z.infer<typeof signalResearchVersionSchema>;
export type SignalRun = z.infer<typeof signalRunSchema>;
export type SignalData = z.infer<typeof signalDataSchema>;
export type SignalStats = z.infer<typeof signalStatsSchema>;
export type SignalResearchArtifactTable = z.infer<typeof signalResearchArtifactTableSchema>;
export type SignalResearchSurface = z.infer<typeof signalResearchSurfaceSchema>;
export type SignalSurfaceArm = z.infer<typeof signalSurfaceArmSchema>;
export type SignalSurfaceIcRow = z.infer<typeof signalSurfaceIcRowSchema>;
export type SignalSurfaceQuantileRow = z.infer<typeof signalSurfaceQuantileRowSchema>;

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function listSignalResearchFamilies(
  signal?: AbortSignal,
): Promise<SignalResearchFamily[]> {
  return getParsed('/api/signals/research/families', z.array(signalResearchFamilySchema), {
    signal,
  });
}

export async function listSignalResearchVersions(
  signalFamily: string,
  signal?: AbortSignal,
): Promise<SignalResearchVersion[]> {
  return getParsed(
    '/api/signals/research/families/{signal_family}/versions',
    z.array(signalResearchVersionSchema),
    {
      params: { path: { signal_family: signalFamily } },
      signal,
    },
  );
}

const RESEARCH_ARTIFACT_PATH =
  '/api/signals/research/families/{signal_family}/versions/{memory_version}/runs/{run_id}/artifacts/{name}';

/** Fetch one JSON artifact of a sealed attempt. Callers own its family-specific shape. */
export async function getSignalResearchArtifactJson(
  signalFamily: string,
  memoryVersion: string,
  runId: string,
  name: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return openapiGet(RESEARCH_ARTIFACT_PATH, {
    params: {
      path: {
        signal_family: signalFamily,
        memory_version: memoryVersion,
        run_id: runId,
        name,
      },
    },
    signal,
  });
}

/** Fetch one parquet artifact of a sealed attempt as bounded rows. */
export async function getSignalResearchArtifactTable(
  signalFamily: string,
  memoryVersion: string,
  runId: string,
  name: string,
  signal?: AbortSignal,
): Promise<SignalResearchArtifactTable> {
  const payload = await getSignalResearchArtifactJson(
    signalFamily,
    memoryVersion,
    runId,
    name,
    signal,
  );
  return signalResearchArtifactTableSchema.parse(payload);
}

export async function getSignalResearchSurface(
  signalFamily: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<SignalResearchSurface> {
  return getParsed(
    '/api/signals/research/families/{signal_family}/versions/{memory_version}/surface',
    signalResearchSurfaceSchema,
    { params: { path: { signal_family: signalFamily, memory_version: memoryVersion } }, signal },
  );
}

const SURFACE_TABLE_PATH =
  '/api/signals/research/families/{signal_family}/versions/{memory_version}/surface/arms/{arm_id}/{table}';

export async function getSignalSurfaceIc(
  signalFamily: string,
  memoryVersion: string,
  armId: string,
  signal?: AbortSignal,
): Promise<SignalSurfaceIcRow[]> {
  const payload = await getParsed(SURFACE_TABLE_PATH, signalSurfaceIcTableSchema, {
    params: {
      path: {
        signal_family: signalFamily,
        memory_version: memoryVersion,
        arm_id: armId,
        table: 'ic',
      },
    },
    signal,
  });
  return payload.rows;
}

export async function getSignalSurfaceQuantiles(
  signalFamily: string,
  memoryVersion: string,
  armId: string,
  signal?: AbortSignal,
): Promise<SignalSurfaceQuantileRow[]> {
  const payload = await getParsed(SURFACE_TABLE_PATH, signalSurfaceQuantileTableSchema, {
    params: {
      path: {
        signal_family: signalFamily,
        memory_version: memoryVersion,
        arm_id: armId,
        table: 'quantiles',
      },
    },
    signal,
  });
  return payload.rows;
}

export async function listSignalRuns(signalId: string, signal?: AbortSignal): Promise<SignalRun[]> {
  return getParsed('/api/signals/{signal_id}', z.array(signalRunSchema), {
    params: { path: { signal_id: signalId } },
    signal,
  });
}

/**
 * Fetch one run payload. Without `asset`, a multi-asset run answers with its latest
 * cross-section; with `asset`, that asset's whole history.
 */
export async function getSignalData(
  signalId: string,
  runId: string,
  asset?: string,
  signal?: AbortSignal,
): Promise<SignalData> {
  return getParsed('/api/signals/{signal_id}/{run_id}', signalDataSchema, {
    params: {
      path: { signal_id: signalId, run_id: runId },
      query: asset ? { asset } : undefined,
    },
    signal,
  });
}

export async function getSignalStats(
  signalId: string,
  runId: string,
  signal?: AbortSignal,
): Promise<SignalStats> {
  return getParsed('/api/signals/{signal_id}/{run_id}/stats', signalStatsSchema, {
    params: { path: { signal_id: signalId, run_id: runId } },
    signal,
  });
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const signalKeys = {
  all: ['signals'] as const,
  list: () => [...signalKeys.all, 'list'] as const,
  researchFamilies: () => [...signalKeys.all, 'research', 'families'] as const,
  researchVersions: (signalFamily: string) =>
    [...signalKeys.researchFamilies(), signalFamily, 'versions'] as const,
  surface: (signalFamily: string, memoryVersion: string) =>
    [...signalKeys.researchVersions(signalFamily), memoryVersion, 'surface'] as const,
  surfaceTable: (
    signalFamily: string,
    memoryVersion: string,
    armId: string,
    table: 'ic' | 'quantiles',
  ) => [...signalKeys.surface(signalFamily, memoryVersion), armId, table] as const,
  runs: (signalId: string) => [...signalKeys.all, 'runs', signalId] as const,
  // `asset` is part of the identity: the same run answers with a cross-section or with
  // one asset's history depending on it.
  data: (signalId: string, runId: string, asset?: string) =>
    [...signalKeys.all, 'data', signalId, runId, asset ?? null] as const,
  stats: (signalId: string, runId: string) =>
    [...signalKeys.all, 'stats', signalId, runId] as const,
  // `form` keeps the raw-JSON and parsed-table readers of one artifact in separate
  // cache entries; the two hooks resolve to different types.
  researchArtifact: (
    signalFamily: string,
    memoryVersion: string,
    runId: string,
    name: string,
    form: 'json' | 'table',
  ) =>
    [
      ...signalKeys.researchVersions(signalFamily),
      memoryVersion,
      runId,
      'artifact',
      name,
      form,
    ] as const,
};

export function useSignalResearchFamilies() {
  return useQuery({
    queryKey: signalKeys.researchFamilies(),
    queryFn: ({ signal }) => listSignalResearchFamilies(signal),
    staleTime: STALE.list,
  });
}

export function useSignalResearchVersions(signalFamily: string) {
  return useQuery({
    queryKey: signalKeys.researchVersions(signalFamily),
    queryFn: ({ signal }) => listSignalResearchVersions(signalFamily, signal),
    staleTime: STALE.list,
    enabled: Boolean(signalFamily),
  });
}

export function useSignalRuns(signalId: string) {
  return useQuery({
    queryKey: signalKeys.runs(signalId),
    queryFn: ({ signal }) => listSignalRuns(signalId, signal),
    // Run listings grow when a new run publishes; refresh like other listings.
    staleTime: STALE.list,
    enabled: Boolean(signalId),
  });
}

export function useSignalData(signalId: string, runId: string, asset?: string) {
  return useQuery({
    queryKey: signalKeys.data(signalId, runId, asset),
    queryFn: ({ signal }) => getSignalData(signalId, runId, asset, signal),
    // Pinned to a run_id; run artifacts publish once and never mutate.
    staleTime: STALE.analysis,
    enabled: Boolean(signalId && runId),
  });
}

export function useSignalStats(signalId: string, runId: string) {
  return useQuery({
    queryKey: signalKeys.stats(signalId, runId),
    queryFn: ({ signal }) => getSignalStats(signalId, runId, signal),
    // Pinned to a run_id; run artifacts publish once and never mutate.
    staleTime: STALE.analysis,
    enabled: Boolean(signalId && runId),
  });
}

/** Sealed attempts publish once and never mutate, so artifacts cache like analysis. */
export function useSignalResearchArtifactJson(
  signalFamily: string,
  memoryVersion: string,
  runId: string,
  name: string,
) {
  return useQuery({
    queryKey: signalKeys.researchArtifact(signalFamily, memoryVersion, runId, name, 'json'),
    queryFn: ({ signal }) =>
      getSignalResearchArtifactJson(signalFamily, memoryVersion, runId, name, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(signalFamily && memoryVersion && runId && name),
  });
}

export function useSignalResearchArtifactTable(
  signalFamily: string,
  memoryVersion: string,
  runId: string,
  name: string,
) {
  return useQuery({
    queryKey: signalKeys.researchArtifact(signalFamily, memoryVersion, runId, name, 'table'),
    queryFn: ({ signal }) =>
      getSignalResearchArtifactTable(signalFamily, memoryVersion, runId, name, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(signalFamily && memoryVersion && runId && name),
  });
}

/** A selected surface can be re-published, so refresh it like a listing. */
export function useSignalResearchSurface(
  signalFamily: string,
  memoryVersion: string,
  enabled = true,
) {
  return useQuery({
    queryKey: signalKeys.surface(signalFamily, memoryVersion),
    queryFn: ({ signal }) => getSignalResearchSurface(signalFamily, memoryVersion, signal),
    staleTime: STALE.list,
    enabled: enabled && Boolean(signalFamily && memoryVersion),
  });
}

/** Arm tables are immutable once published. */
export function useSignalSurfaceIc(signalFamily: string, memoryVersion: string, armId: string) {
  return useQuery({
    queryKey: signalKeys.surfaceTable(signalFamily, memoryVersion, armId, 'ic'),
    queryFn: ({ signal }) => getSignalSurfaceIc(signalFamily, memoryVersion, armId, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(signalFamily && memoryVersion && armId),
  });
}

export function useSignalSurfaceQuantiles(
  signalFamily: string,
  memoryVersion: string,
  armId: string,
) {
  return useQuery({
    queryKey: signalKeys.surfaceTable(signalFamily, memoryVersion, armId, 'quantiles'),
    queryFn: ({ signal }) => getSignalSurfaceQuantiles(signalFamily, memoryVersion, armId, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(signalFamily && memoryVersion && armId),
  });
}
