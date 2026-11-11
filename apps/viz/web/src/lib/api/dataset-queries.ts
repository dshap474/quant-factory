/**
 * Cached query hooks for dataset previews and feature-profile inspection.
 *
 * USAGE:
 *   const preview = useDatasetPreview('data', path, page, pageSize);
 *   const profile = useDatasetProfile('features', path, params);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';
import { z } from 'zod';
import {
  type DatasetScope,
  listCatalog,
  previewDatasetChartValues,
  previewDatasetParquet,
  profileDatasetFeatureDetail,
  profileDatasetFeatures,
  queryDatasetParquet,
} from './catalog';
import { requestParsed } from './client';
import { browseFeatureFiles } from './features';
import { encodePath } from './paths';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Types and keys
// --------------------------------------------------------------------------- #

export type { DatasetScope } from './catalog';

export interface DatasetProfileParams {
  preset?: string;
  query?: string;
  family?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  entity_column?: string | null;
  entity_value?: string | null;
  max_spark_points?: number;
}

/** One-entity row filter; both halves are required before the server sees either. */
export interface DatasetEntityFilter {
  entityColumn?: string | null;
  entityValue?: string | null;
}

export interface DatasetProfileDetailParams {
  column: string;
  entity_column?: string | null;
  entity_value?: string | null;
  max_spark_points?: number;
}

const datasetSchemaResponseSchema = z.object({
  scope: z.enum(['data', 'features']),
  path: z.string(),
  total_rows: z.number(),
  schema: z.array(z.object({ name: z.string(), dtype: z.string() })),
});

export const datasetQueryKeys = {
  all: ['dataset-query'] as const,
  preview: (scope: DatasetScope, path: string, page: number, rowCount: number) =>
    [...datasetQueryKeys.all, 'preview', scope, path, page, rowCount] as const,
  schema: (scope: DatasetScope, path: string) =>
    [...datasetQueryKeys.all, 'schema', scope, path] as const,
  rows: (
    scope: DatasetScope,
    path: string,
    page: number,
    rowCount: number,
    columns: string[],
    entity: DatasetEntityFilter,
  ) =>
    [
      ...datasetQueryKeys.all,
      'rows',
      scope,
      path,
      page,
      rowCount,
      columns,
      entity.entityColumn ?? null,
      entity.entityValue ?? null,
    ] as const,
  profile: (scope: DatasetScope, path: string, params: DatasetProfileParams) =>
    [...datasetQueryKeys.all, 'profile', scope, path, params] as const,
  profileDetail: (scope: DatasetScope, path: string, params: DatasetProfileDetailParams) =>
    [...datasetQueryKeys.all, 'profile-detail', scope, path, params] as const,
  listing: (scope: DatasetScope, path: string) =>
    [...datasetQueryKeys.all, 'listing', scope, path] as const,
  entityValues: (scope: DatasetScope, path: string, entityColumn: string, query: string) =>
    [...datasetQueryKeys.all, 'entity-values', scope, path, entityColumn, query] as const,
};

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

/** Directory listing for the lake explorer; a new path skeletons rather than showing the old one. */
export function useDatasetListing(scope: DatasetScope, path: string) {
  return useQuery({
    queryKey: datasetQueryKeys.listing(scope, path),
    queryFn: ({ signal }) =>
      (scope === 'features' ? browseFeatureFiles : listCatalog)(path, signal),
    staleTime: STALE.catalog,
  });
}

export function useDatasetPreview(
  scope: DatasetScope,
  path: string,
  page: number,
  rowCount: number,
  enabled = true,
) {
  return useQuery({
    queryKey: datasetQueryKeys.preview(scope, path, page, rowCount),
    queryFn: ({ signal }) => previewDatasetParquet(scope, path, page, rowCount, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE.catalog,
    enabled: Boolean(path && enabled),
  });
}

export function useDatasetSchema(scope: DatasetScope, path: string, enabled = true) {
  return useQuery({
    queryKey: datasetQueryKeys.schema(scope, path),
    queryFn: ({ signal }) =>
      requestParsed(
        `/api/datasets/${scope}/schema/${encodePath(path)}`,
        datasetSchemaResponseSchema,
        {
          signal,
        },
      ),
    staleTime: STALE.catalog,
    enabled: Boolean(path && enabled),
  });
}

export function useDatasetRows(
  scope: DatasetScope,
  path: string,
  page: number,
  rowCount: number,
  columns: string[],
  enabled = true,
  entity: DatasetEntityFilter = {},
) {
  return useQuery({
    queryKey: datasetQueryKeys.rows(scope, path, page, rowCount, columns, entity),
    queryFn: ({ signal }) =>
      queryDatasetParquet(
        scope,
        path,
        {
          limit: rowCount,
          offset: (page - 1) * rowCount,
          columns,
          entity_column: entity.entityColumn ?? null,
          entity_value: entity.entityValue ?? null,
        },
        signal,
      ),
    placeholderData: keepPreviousData,
    staleTime: STALE.catalog,
    enabled: Boolean(path && columns.length && enabled),
  });
}

export function useDatasetProfile(scope: DatasetScope, path: string, params: DatasetProfileParams) {
  return useQuery({
    queryKey: datasetQueryKeys.profile(scope, path, params),
    queryFn: ({ signal }) => profileDatasetFeatures(scope, path, params, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE.catalog,
    enabled: Boolean(path),
  });
}

export function useDatasetProfileDetail(
  scope: DatasetScope,
  path: string,
  params: DatasetProfileDetailParams | null,
) {
  const resolvedParams = params ?? { column: '' };
  return useQuery({
    queryKey: datasetQueryKeys.profileDetail(scope, path, resolvedParams),
    queryFn: ({ signal }) => profileDatasetFeatureDetail(scope, path, resolvedParams, signal),
    staleTime: STALE.catalog,
    enabled: Boolean(path && params?.column),
  });
}

/** Stable `labelOf` for SearchSelect from a chart-values response's label map. */
export function useEntityLabelOf(labels: Record<string, string> | undefined) {
  return useCallback((value: string) => labels?.[value], [labels]);
}

/**
 * Enough for every entity of the widest dataset (an asset roster can reach tens of thousands of symbols),
 * so pickers search the full roster locally. Render values only through the virtualized
 * SearchSelect; a plain Select mounts every option and freezes the page at this size.
 */
export const ENTITY_VALUE_LIMIT = 50_000;

/**
 * Distinct values of one entity column, up to ENTITY_VALUE_LIMIT. `query` narrows them
 * server-side.
 */
export function useDatasetEntityValues(
  scope: DatasetScope,
  path: string,
  entityColumn: string,
  query = '',
) {
  return useQuery({
    queryKey: datasetQueryKeys.entityValues(scope, path, entityColumn, query),
    queryFn: ({ signal }) =>
      previewDatasetChartValues(
        scope,
        path,
        { entity_column: entityColumn, query, limit: ENTITY_VALUE_LIMIT, offset: 0 },
        signal,
      ),
    staleTime: STALE.catalog,
    enabled: Boolean(path && entityColumn),
  });
}
