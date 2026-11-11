/**
 * Canonical agents inventory API.
 *
 * USAGE:
 *   const { data } = useAgents();
 *   const { data: prompts } = useAgentPrompts('strategy-optimizer');
 *   const { data: readme } = useAgentReadme('strategy-optimizer');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { requestParsed } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schemas
// --------------------------------------------------------------------------- #

export const agentSummarySchema = z.object({
  id: z.string(),
  name: z.string(),
  path: z.string(),
  status: z.string(),
  program_ready: z.boolean(),
  driver_ready: z.boolean(),
  tests_ready: z.boolean(),
  prompt_steps: z.array(z.string()),
  bindings: z
    .array(
      z.object({
        stage: z.string(),
        engine: z.string().nullable(),
        model: z.string().nullable(),
        effort: z.string().nullable(),
      }),
    )
    .default([]),
});

export const agentReadmeSchema = z.object({
  id: z.string(),
  name: z.string(),
  path: z.string(),
  markdown: z.string(),
});

export const agentPromptSchema = z.object({
  id: z.string(),
  kind: z.enum(['resident-common', 'resident-stage', 'meta']),
  stage: z.number().int().nonnegative().nullable(),
  name: z.string(),
  path: z.string(),
  markdown: z.string(),
});

export const agentPromptsSchema = z.object({
  id: z.string(),
  name: z.string(),
  prompts: z.array(agentPromptSchema),
});

export const agentsResponseSchema = z.object({
  agents: z.array(agentSummarySchema),
  count: z.number(),
  documented_loop_count: z.number(),
  canonical_root: z.string(),
  documentation_root: z.string(),
});

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type AgentSummary = z.infer<typeof agentSummarySchema>;
export type AgentsResponse = z.infer<typeof agentsResponseSchema>;
export type AgentReadme = z.infer<typeof agentReadmeSchema>;
export type AgentPrompt = z.infer<typeof agentPromptSchema>;
export type AgentPrompts = z.infer<typeof agentPromptsSchema>;

// --------------------------------------------------------------------------- #
// Fetcher
// --------------------------------------------------------------------------- #

export async function getAgents(signal?: AbortSignal): Promise<AgentsResponse> {
  return requestParsed('/api/agents', agentsResponseSchema, { signal });
}

export async function getAgentReadme(agentId: string, signal?: AbortSignal): Promise<AgentReadme> {
  return requestParsed(`/api/agents/${encodeURIComponent(agentId)}/readme`, agentReadmeSchema, {
    signal,
  });
}

export async function getAgentPrompts(
  agentId: string,
  signal?: AbortSignal,
): Promise<AgentPrompts> {
  return requestParsed(`/api/agents/${encodeURIComponent(agentId)}/prompts`, agentPromptsSchema, {
    signal,
  });
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: ({ signal }) => getAgents(signal),
    staleTime: STALE.catalog,
  });
}

export function useAgentReadme(agentId: string) {
  return useQuery({
    queryKey: ['agents', agentId, 'readme'],
    queryFn: ({ signal }) => getAgentReadme(agentId, signal),
    staleTime: STALE.catalog,
    enabled: Boolean(agentId),
  });
}

export function useAgentPrompts(agentId: string) {
  return useQuery({
    queryKey: ['agents', agentId, 'prompts'],
    queryFn: ({ signal }) => getAgentPrompts(agentId, signal),
    staleTime: STALE.catalog,
    enabled: Boolean(agentId),
  });
}
