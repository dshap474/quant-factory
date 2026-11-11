/**
 * Strategy version records API — a version's VERSION.toml and record documents, and the
 * family's lineage rows (one per version) for the evolution view.
 *
 * USAGE:
 *   const { data } = useStrategyVersionRecords('example', 'v002');
 *   data?.record.status; data?.documents.map((doc) => doc.name);
 *   const { data: rows } = useStrategyFamilyVersions('example');
 *   const { data: signalRows } = useStrategyFamilyVersions('example', 'signals');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import type { FamilyPackage } from '@/lib/strategy-docs';
import { requestParsed } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export const strategyVersionRecordsSchema = z.object({
  strategy_type: z.string(),
  memory_version: z.string(),
  path: z.string(),
  record: z.record(z.string(), z.unknown()),
  documents: z.array(z.object({ name: z.string(), markdown: z.string() })),
});

export type StrategyVersionRecords = z.infer<typeof strategyVersionRecordsSchema>;

export const strategyLineageRowSchema = z.object({
  version: z.string(),
  status: z.string().nullable(),
  phase: z.string().nullable(),
  parent: z.string().nullable(),
  question: z.string().nullable(),
  finding: z.string().nullable(),
  backtest_run_at: z.string().nullable(),
  baseline_selected_at: z.string().nullable(),
  /** `[headline]` as recorded; families differ in value types, so readers type-check fields. */
  headline: z.record(z.string(), z.unknown()).nullable(),
});

export type StrategyLineageRow = z.infer<typeof strategyLineageRowSchema>;

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function getStrategyVersionRecords(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<StrategyVersionRecords> {
  return requestParsed(
    `/api/strategy-versions/${encodeURIComponent(strategyType)}/${encodeURIComponent(memoryVersion)}/records`,
    strategyVersionRecordsSchema,
    { signal },
  );
}

/** Lineage rows of a strategy family, or of a signal family with `pkg = 'signals'`. */
export async function getStrategyFamilyVersions(
  strategyType: string,
  pkg: FamilyPackage = 'strategies',
  signal?: AbortSignal,
): Promise<StrategyLineageRow[]> {
  const family = encodeURIComponent(strategyType);
  return requestParsed(
    pkg === 'signals'
      ? `/api/signals/research/families/${family}/lineage`
      : `/api/strategy-versions/${family}`,
    z.array(strategyLineageRowSchema),
    { signal },
  );
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export function useStrategyVersionRecords(strategyType: string, memoryVersion: string) {
  return useQuery({
    queryKey: ['strategy-version-records', strategyType, memoryVersion] as const,
    queryFn: ({ signal }) => getStrategyVersionRecords(strategyType, memoryVersion, signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType && memoryVersion),
    retry: false,
  });
}

export function useStrategyFamilyVersions(strategyType: string, pkg: FamilyPackage = 'strategies') {
  return useQuery({
    queryKey: ['strategy-family-versions', pkg, strategyType] as const,
    queryFn: ({ signal }) => getStrategyFamilyVersions(strategyType, pkg, signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType),
    retry: false,
  });
}
