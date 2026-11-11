/**
 * Validated read-only projections of the shared agent run store.
 * USAGE: const query = useAgentRuns();
 */

// --------------------------------------------------------------------------- #
// Imports and schemas
// --------------------------------------------------------------------------- #

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';

const instant = z.iso.datetime({ offset: true }).nullable();
const seconds = z.number().finite().nonnegative().nullable();
const units = z.number().int().nonnegative().nullable();

export const agentStepSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  name: z.string(),
  work_item: z.string().nullable(),
  status: z.enum([
    'running',
    'checking',
    'succeeded',
    'failed',
    'cancelled',
    'interrupted',
    'unknown',
  ]),
  started_at: instant,
  finished_at: instant,
  engine: z.string().nullable(),
  model: z.string().nullable(),
  reasoning: z.string().nullable(),
  activity: z.string().nullable(),
  activity_source: z.enum(['runner', 'provider', 'agent']).nullable(),
  updated_at: instant,
  completed_units: units,
  total_units: units,
  exit_code: z.number().int().nullable(),
  error: z.string().nullable(),
  elapsed_seconds: seconds,
  input_tokens: units.default(null),
  output_tokens: units.default(null),
  cache_read_tokens: units.default(null),
  cache_write_tokens: units.default(null),
  thinking_tokens: units.default(null),
  cost_usd: seconds.default(null),
  cost_basis: z.string().nullable().default(null),
  wall_seconds: seconds.default(null),
  artifacts: z
    .object({
      directory: z.string().nullable(),
      report_available: z.boolean(),
      usage: z.object({
        input_tokens: seconds,
        output_tokens: seconds,
        cache_read_tokens: seconds,
        cache_write_tokens: seconds.default(null),
        thinking_tokens: seconds,
        total_tokens: seconds,
        wall_seconds: seconds,
        cost_usd: seconds,
        cost_basis: z.string().nullable(),
      }),
    })
    .optional(),
});
const stepStatus = agentStepSchema.shape.status;

export const runTotalsSchema = z.object({
  input_tokens: units,
  output_tokens: units,
  cache_read_tokens: units,
  cache_write_tokens: units,
  thinking_tokens: units,
  cost_usd: seconds,
  wall_seconds: seconds,
  steps_with_usage: z.number().int().nonnegative(),
  cost_complete: z.boolean(),
});
export const runStageSchema = z.object({
  name: z.string(),
  status: stepStatus,
  counts: z.record(z.string(), z.number().int().nonnegative()),
  count: z.number().int().nonnegative(),
  started_at: instant,
  finished_at: instant,
  elapsed_seconds: seconds,
  cost_usd: seconds,
  models: z.array(z.string()),
});

export const agentRunSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  target: z.string().nullable(),
  status: z.enum([
    'starting',
    'running',
    'succeeded',
    'failed',
    'cancelled',
    'interrupted',
    'unknown',
  ]),
  started_at: instant,
  finished_at: instant,
  heartbeat_at: instant,
  host_id: z.string().nullable().default(null),
  resumed_from_run_id: z.string().nullable(),
  error: z.string().nullable(),
  legacy_source: z.string().nullable(),
  elapsed_seconds: seconds,
  health: z.enum(['responsive', 'unresponsive', 'interrupted', 'unknown', 'not-applicable']),
  health_detail: z.string().nullable(),
  active_steps: z.array(agentStepSchema),
  active_step_count: z.number().int().nonnegative(),
  step_counts: z.record(z.string(), z.number().int().nonnegative()),
  step_total: z.number().int().nonnegative(),
  last_step: agentStepSchema.nullable(),
  last_activity_at: instant,
  unresolved: z.boolean(),
  label: z.string().nullable().default(null),
  subject_run_id: z.string().nullable().default(null),
  subject: z
    .object({
      id: z.string(),
      agent_id: z.string(),
      label: z.string().nullable(),
      target: z.string().nullable(),
      status: z.string(),
    })
    .nullable()
    .default(null),
  reviews: z
    .array(z.object({ id: z.string(), status: z.string(), started_at: instant }))
    .default([]),
  attempt: z
    .object({ number: z.number().int().positive(), count: z.number().int().positive() })
    .nullable()
    .default(null),
  totals: runTotalsSchema.nullable().default(null),
  stages: z.array(runStageSchema).default([]),
});
export const agentRunsSchema = z.object({
  fetched_at: z.iso.datetime({ offset: true }),
  store: z.object({
    available: z.boolean(),
    schema_version: z.number().int().nullable(),
    detail: z.string().nullable(),
  }),
  runs: z.array(agentRunSchema),
  coverage: z.array(
    z.object({
      agent_id: z.string(),
      name: z.string(),
      status: z.enum(['monitored', 'not-monitored', 'unregistered']),
      steps: z.array(z.string()),
      records: z.number().int().nonnegative(),
      detail: z.string(),
    }),
  ),
  active_count: z.number().int().nonnegative(),
  attention_count: z.number().int().nonnegative(),
  unresolved_count: z.number().int().nonnegative(),
  history_total: z.number().int().nonnegative(),
  history_limit: z.number().int().nonnegative(),
  steps_truncated: z.boolean(),
  process_snapshot_available: z.boolean(),
  host_id: z.string().nullable(),
});
export const agentRunDetailSchema = z.object({
  run: agentRunSchema,
  locations: z.array(z.object({ label: z.string(), path: z.string() })).optional(),
  steps: z.array(agentStepSchema),
  step_total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
  fetched_at: z.iso.datetime({ offset: true }),
});
export const agentRunActivitySchema = z.object({
  run_id: z.string(),
  entries: z.array(
    z.object({
      at: z.iso.datetime({ offset: true }),
      step_id: z.string().nullable(),
      source: z.enum(['runner', 'provider', 'agent']),
      text: z.string(),
    }),
  ),
  available: z.boolean(),
  truncated: z.boolean(),
  malformed: z.number().int().nonnegative(),
});
const dailySchema = z.object({
  date: z.string(),
  succeeded: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  other: z.number().int().nonnegative(),
  cost_usd: seconds,
});
export const agentRunStatsSchema = z.object({
  fetched_at: z.iso.datetime({ offset: true }),
  days: z.number().int().positive(),
  window: z.object({
    runs_24h: z.number().int().nonnegative(),
    failed_24h: z.number().int().nonnegative(),
    cost_24h: seconds,
    cost_7d: seconds,
    cost_complete_7d: z.boolean(),
    last_finished_at: instant,
  }),
  agents: z.array(
    z.object({
      agent_id: z.string(),
      last_run: z
        .object({
          id: z.string(),
          status: z.string(),
          started_at: instant,
          label: z.string().nullable(),
        })
        .nullable(),
      runs_7d: z.number().int().nonnegative(),
      failed_7d: z.number().int().nonnegative(),
      cost_7d: seconds,
      p50_elapsed_seconds_7d: seconds,
      daily: z.array(dailySchema),
    }),
  ),
});
export type AgentRunStats = z.infer<typeof agentRunStatsSchema>;
export type AgentRunStage = z.infer<typeof runStageSchema>;
export type AgentRun = z.infer<typeof agentRunSchema>;
export type AgentStep = z.infer<typeof agentStepSchema>;
export type AgentRuns = z.infer<typeof agentRunsSchema>;
export type AgentRunDetail = z.infer<typeof agentRunDetailSchema>;
export type AgentRunActivity = z.infer<typeof agentRunActivitySchema>;

// --------------------------------------------------------------------------- #
// Fetch and polling
// --------------------------------------------------------------------------- #

const LIVE_POLL_MS = 2_000;

const reportSchema = z.object({ text: z.string(), truncated: z.boolean() });

/** Reports are fetched only after an explicit expansion, and rendered as plain text. */
export function useAgentStepReport(runId: string, stepId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['agent-step-report', runId, stepId],
    queryFn: ({ signal }) =>
      readJson(
        `/api/agents/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}/report`,
        reportSchema,
        signal,
      ),
    enabled,
    staleTime: 0,
    retry: false,
  });
}

async function readJson<T>(
  path: string,
  schema: z.ZodType<T>,
  signal: AbortSignal | undefined,
): Promise<T> {
  const timeout = AbortSignal.timeout(8_000);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  return requestParsed(path, schema, { signal: requestSignal, cache: 'no-store' });
}

export interface AgentRunsFilter {
  agentId?: string | undefined;
  status?: AgentRun['status'] | undefined;
}

/** Latest attempt per target, newest first, at the API's history bound. */
export async function getAgentRuns(
  signal?: AbortSignal,
  filter: AgentRunsFilter = {},
): Promise<AgentRuns> {
  const params = new URLSearchParams({ history_limit: '100', latest_attempts_only: 'true' });
  if (filter.agentId) params.set('agent_id', filter.agentId);
  if (filter.status) params.set('status', filter.status);
  return readJson(`/api/agents/runs?${params}`, agentRunsSchema, signal);
}

export async function getAgentRunStats(signal?: AbortSignal): Promise<AgentRunStats> {
  return readJson('/api/agents/runs/stats?days=14', agentRunStatsSchema, signal);
}

/** Every step of one run, paged at the API's 200-row bound (capped at 1,000 steps). */
export async function getAgentRunSteps(
  runId: string,
  signal?: AbortSignal,
): Promise<AgentRunDetail> {
  const path = `/api/agents/runs/${encodeURIComponent(runId)}?limit=200`;
  const first = await readJson(`${path}&offset=0`, agentRunDetailSchema, signal);
  const steps = [...first.steps];
  while (steps.length < Math.min(first.step_total, 1_000)) {
    const page = await readJson(`${path}&offset=${steps.length}`, agentRunDetailSchema, signal);
    if (page.steps.length === 0) break;
    steps.push(...page.steps);
  }
  return { ...first, steps };
}

export async function getAgentRun(
  runId: string,
  signal?: AbortSignal,
  offset = 0,
): Promise<AgentRunDetail> {
  return readJson(
    `/api/agents/runs/${encodeURIComponent(runId)}?limit=12&offset=${offset}`,
    agentRunDetailSchema,
    signal,
  );
}

export async function getAgentRunActivity(
  runId: string,
  signal?: AbortSignal,
  limit = 20,
): Promise<AgentRunActivity> {
  return readJson(
    `/api/agents/runs/${encodeURIComponent(runId)}/activity?limit=${limit}`,
    agentRunActivitySchema,
    signal,
  );
}

export function useAgentRuns(filter: AgentRunsFilter = {}) {
  return useQuery({
    queryKey: ['agent-runs', filter.agentId ?? null, filter.status ?? null],
    queryFn: ({ signal }) => getAgentRuns(signal, filter),
    refetchInterval: LIVE_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: 'always',
    staleTime: 0,
    retry: false,
  });
}

/** Expanded rows only: steps and their feed are never loaded for the whole list. */
export function useAgentRunDetail(runId: string | null, live: boolean, offset = 0) {
  return useQuery({
    queryKey: ['agent-run', runId, offset],
    queryFn: ({ signal }) => getAgentRun(runId as string, signal, offset),
    placeholderData: keepPreviousData,
    enabled: runId !== null,
    refetchInterval: live ? LIVE_POLL_MS : false,
    refetchIntervalInBackground: false,
    staleTime: 0,
    retry: false,
  });
}

export function useAgentRunStats() {
  return useQuery({
    queryKey: ['agent-run-stats'],
    queryFn: ({ signal }) => getAgentRunStats(signal),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 0,
    retry: false,
  });
}

/** The run page reads every step at once; polls while the run is starting or running. */
export function useAgentRunSteps(runId: string) {
  return useQuery({
    queryKey: ['agent-run-steps', runId],
    queryFn: ({ signal }) => getAgentRunSteps(runId, signal),
    refetchInterval: (query) =>
      ['starting', 'running'].includes(query.state.data?.run.status ?? 'running')
        ? LIVE_POLL_MS
        : false,
    refetchIntervalInBackground: false,
    staleTime: 0,
    retry: false,
  });
}

export function useAgentRunActivity(runId: string | null, live: boolean, limit = 20) {
  return useQuery({
    queryKey: ['agent-run-activity', runId, limit],
    queryFn: ({ signal }) => getAgentRunActivity(runId as string, signal, limit),
    enabled: runId !== null,
    refetchInterval: live ? LIVE_POLL_MS : false,
    refetchIntervalInBackground: false,
    staleTime: 0,
    retry: false,
  });
}
