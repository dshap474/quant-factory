/**
 * Validated publication sidecar of one published feature panel: the per-column
 * contract in `meta.yaml`.
 *
 * USAGE:
 *   const meta = useFeaturePanelMeta(path);
 */

// --------------------------------------------------------------------------- #
// Schemas
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';
import { encodePath } from './paths';
import { STALE } from './stale-times';

const panelMetaColumnSchema = z.object({
  name: z.string(),
  formula: z.string().nullable(),
  unit: z.string().nullable(),
  dependencies: z.array(z.string()),
  non_null_rows: z.number().nullable(),
  first_non_null: z.string().nullable(),
  last_non_null: z.string().nullable(),
});

const panelMetaFreshnessSchema = z.object({
  source: z.string(),
  path: z.string().nullable(),
  present: z.boolean(),
  captured_at: z.string().nullable(),
  min_available: z.string().nullable(),
  max_available: z.string().nullable(),
});

const panelOwedSchema = z.object({
  summary: z.string().nullable(),
  reason: z.string().nullable(),
  columns_that_will_change: z.array(z.string()),
  columns_that_will_be_added: z.array(z.string()),
  columns_unchanged: z.array(z.string()),
});

export const featurePanelMetaSchema = z.object({
  path: z.string(),
  category: z.string(),
  present: z.boolean(),
  name: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  created_by: z.string().nullable().optional(),
  columns: z.array(panelMetaColumnSchema),
  as_of: z.record(z.string(), z.unknown()).optional(),
  scope: z.record(z.string(), z.unknown()).optional(),
  freshness: z.array(panelMetaFreshnessSchema),
  // Work the publication itself declares still owed, e.g. a broad panel left stale.
  owed: panelOwedSchema.nullable().optional(),
});

export type FeaturePanelMeta = z.infer<typeof featurePanelMetaSchema>;
export type FeaturePanelMetaColumn = z.infer<typeof panelMetaColumnSchema>;
export type FeaturePanelOwed = z.infer<typeof panelOwedSchema>;

// --------------------------------------------------------------------------- #
// Queries
// --------------------------------------------------------------------------- #

export function useFeaturePanelMeta(path: string) {
  return useQuery({
    queryKey: ['features', 'panel-meta', path],
    queryFn: ({ signal }) =>
      requestParsed(`/api/features/panel-meta/${encodePath(path)}`, featurePanelMetaSchema, {
        signal,
      }),
    enabled: Boolean(path),
    staleTime: STALE.catalog,
  });
}
