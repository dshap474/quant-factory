/** Read-only Information Compression configuration and paginated run history.
 * USAGE: useInformationCompressionHistory({ mode: 'history', limit: 5 });
 */

// --------------------------------------------------------------------------- #
// Schemas and polling
// --------------------------------------------------------------------------- #
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { agentRunSchema } from './agent-runs';
import { requestParsed } from './client';

const entrySchema = z.object({ run: agentRunSchema, attempt_count: z.number().int().positive() });
const pageSchema = z.object({
  total: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
});
const historySchema = pageSchema.extend({ entries: z.array(entrySchema) });
const attemptsSchema = pageSchema.extend({ runs: z.array(agentRunSchema) });
export type InformationCompressionEntry = z.infer<typeof entrySchema>;

function useCompressionQuery<T>(path: string, schema: z.ZodType<T>, live = true) {
  return useQuery({
    queryKey: ['information-compression', path],
    queryFn: ({ signal }): Promise<T> =>
      requestParsed(`/api/agents/information-compression/${path}`, schema, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(8_000)]),
        cache: 'no-store',
      }),
    placeholderData: keepPreviousData,
    refetchInterval: live ? 2_000 : false,
    refetchIntervalInBackground: false,
    retry: false,
    staleTime: 0,
  });
}

export function useInformationCompressionHistory(filters: {
  mode: 'all' | 'active' | 'history';
  query?: string;
  status?: string;
  since?: string;
  limit: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== '') params.set(key, String(value));
  }
  return useCompressionQuery(`history?${params}`, historySchema);
}

export function useInformationCompressionAttempts(runId: string, offset: number) {
  return useCompressionQuery(
    `attempts/${encodeURIComponent(runId)}?offset=${offset}`,
    attemptsSchema,
  );
}
