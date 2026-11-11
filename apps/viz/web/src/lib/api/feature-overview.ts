/**
 * Validated family overview and preset diagnostics for one published snapshot.
 * USAGE: const overview = useFeatureOverview(path);
 */

// --------------------------------------------------------------------------- #
// Schema and query
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';
import { encodePath } from './paths';
import { STALE } from './stale-times';

const summarySchema = z.object({
  features: z.number(),
  coverage: z.number().nullable(),
  null_cells: z.number(),
  invalid_cells: z.number(),
  empty_features: z.number(),
  constant_features: z.number(),
});
const coverageSchema = z.array(
  z.object({
    timestamp: z.string(),
    assets: z.number(),
    rows: z.number(),
    coverage: z.number().nullable(),
  }),
);
const presetSchema = z.object({
  name: z.string(),
  description: z.string(),
  kind: z.enum(['full', 'subset', 'configuration']),
  available: z.boolean(),
  columns: z.array(z.string()),
  declared_features: z.number().nullable(),
  missing_columns: z.array(z.string()),
  definition_changes: z.array(z.string()),
  configured_blocks: z.array(z.string()),
  summary: summarySchema.nullable(),
  coverage: coverageSchema,
  blocks: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      summary: summarySchema,
      coverage: coverageSchema,
      latest: z.string().nullable(),
    }),
  ),
});
export const featureOverviewSchema = z.object({
  path: z.string(),
  category: z.string(),
  default_preset: z.string(),
  build: z.object({
    id: z.string(),
    published_at: z.string().nullable(),
    rows: z.number(),
    assets: z.number(),
    start: z.string().nullable(),
    end: z.string().nullable(),
    features: z.number(),
    keys: z.array(z.string()),
  }),
  presets: z.array(presetSchema),
  analysis: z.object({
    correlation: z.enum(['missing', 'unverified']),
    ic: z.enum(['missing', 'unverified', 'stale', 'verified']),
  }),
});
export type FeatureOverview = z.infer<typeof featureOverviewSchema>;
export type FeaturePresetOverview = z.infer<typeof presetSchema>;

export function useFeatureOverview(
  path: string,
  {
    diagnostics = true,
    enabled = true,
    snapshotId,
  }: {
    diagnostics?: boolean;
    enabled?: boolean;
    snapshotId?: string;
  } = {},
) {
  return useQuery({
    queryKey: ['features', 'overview', path, diagnostics, snapshotId],
    queryFn: ({ signal }) =>
      requestParsed(
        `/api/features/overview/${encodePath(path)}?diagnostics=${diagnostics}`,
        featureOverviewSchema,
        {
          signal,
        },
      ),
    enabled: Boolean(path) && enabled,
    staleTime: STALE.catalog,
  });
}
