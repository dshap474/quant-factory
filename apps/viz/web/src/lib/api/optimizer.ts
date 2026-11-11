/** Strategy Optimizer's read-only workflow, target history and documents.
 * USAGE: useOptimizerHistory({ mode: 'history', limit: 5 });
 */

// --------------------------------------------------------------------------- #
// Validated API boundary
// --------------------------------------------------------------------------- #
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { agentRunDetailSchema } from './agent-runs';
import { requestParsed } from './client';

const entrySchema = z.object({
  detail: agentRunDetailSchema,
  attempt_count: z.number().int().positive(),
  document_paths: z.record(z.string(), z.string()).optional(),
  file_roots: z.record(z.string(), z.string()).optional(),
  research: z.object({
    status: z.enum(['supported', 'falsified', 'not_tested']).nullable(),
    surface_url: z
      .string()
      .regex(/^\/strategies\/[A-Za-z0-9_-]+\/v[0-9]+$/)
      .nullable()
      .optional(),
    documents: z.array(z.enum(['spec', 'review', 'outcome'])),
  }),
});
const page = {
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
};
const historySchema = z.object({ entries: z.array(entrySchema), ...page });
const attemptsSchema = z.object({ attempts: z.array(agentRunDetailSchema), ...page });
const filesSchema = z.object({
  path: z.string(),
  location: z.string(),
  truncated: z.boolean(),
  entries: z.array(
    z.object({
      name: z.string(),
      path: z.string(),
      directory: z.boolean(),
      bytes: z.number().nullable(),
    }),
  ),
});
const fileSchema = z.object({
  name: z.string(),
  path: z.string(),
  location: z.string(),
  bytes: z.number(),
  text: z.string().nullable(),
  markdown: z.boolean(),
  truncated: z.boolean(),
});
export type OptimizerFileScope = 'version' | 'attempt' | 'research';
export type OptimizerEntry = z.infer<typeof entrySchema>;
export type OptimizerFilters = {
  mode?: 'all' | 'active' | 'history';
  query?: string;
  status?: string;
  since?: string;
  limit?: number;
  offset?: number;
};
const base = '/api/agents/strategy-optimizer';

async function read<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal): Promise<T> {
  return requestParsed(`${base}${path}`, schema, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
    cache: 'no-store',
  });
}

// --------------------------------------------------------------------------- #
// Queries: live summaries; expanded evidence only on demand
// --------------------------------------------------------------------------- #
export function useOptimizerHistory(filters: OptimizerFilters) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters))
    if (value !== undefined && value !== '') params.set(key, String(value));
  return useQuery({
    queryKey: ['optimizer-history', filters],
    queryFn: ({ signal }) => read(`/history?${params}`, historySchema, signal),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      (query.state.data?.entries ?? []).some((entry) =>
        ['starting', 'running'].includes(entry.detail.run.status),
      )
        ? 2_000
        : false,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
export function useOptimizerAttempts(runId: string, offset: number, live = true) {
  return useQuery({
    queryKey: ['optimizer-attempts', runId, offset],
    queryFn: ({ signal }) =>
      read(`/attempts/${encodeURIComponent(runId)}?offset=${offset}`, attemptsSchema, signal),
    refetchInterval: live ? 2_000 : false,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
export function useOptimizerRun(runId: string) {
  return useQuery({
    queryKey: ['optimizer-run', runId],
    queryFn: ({ signal }) => read(`/runs/${encodeURIComponent(runId)}`, entrySchema, signal),
    refetchInterval: (query) =>
      ['starting', 'running'].includes(query.state.data?.detail.run.status ?? '') ? 2_000 : false,
    retry: false,
  });
}

export function optimizerFileUrl(runId: string, scope: OptimizerFileScope, path: string) {
  return `${base}/file/${encodeURIComponent(runId)}?${new URLSearchParams({ scope, path })}`;
}

export function useOptimizerFiles(
  runId: string,
  scope: OptimizerFileScope,
  path: string,
  live: boolean,
) {
  return useQuery({
    queryKey: ['optimizer-files', runId, scope, path],
    queryFn: ({ signal }) =>
      read(
        `/files/${encodeURIComponent(runId)}?${new URLSearchParams({ scope, path })}`,
        filesSchema,
        signal,
      ),
    refetchInterval: live ? 5_000 : false,
    retry: false,
  });
}

export function useOptimizerFile(
  runId: string,
  scope: OptimizerFileScope,
  path: string | null,
  live: boolean,
) {
  return useQuery({
    queryKey: ['optimizer-file', runId, scope, path],
    queryFn: ({ signal }) =>
      read(
        `/file/${encodeURIComponent(runId)}?${new URLSearchParams({ scope, path: path ?? '' })}`,
        fileSchema,
        signal,
      ),
    enabled: path !== null,
    refetchInterval: live ? 5_000 : false,
    retry: false,
  });
}
