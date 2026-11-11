/**
 * Catalog API — lake browser, previews, charts, feature profiles.
 *
 * USAGE:
 *   const { data } = useCatalog();
 *   const { data: stats } = useCatalogStats();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed, requestJson, requestParsed } from './client';
import { encodePath } from './paths';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export const catalogItemSchema = z.object({
  name: z.string(),
  label: z.string().optional(),
  is_dir: z.boolean(),
  size: z.number().nullable(),
  modified: z.number(),
  type: z.string(),
});

export const catalogListingSchema = z.object({
  path: z.string(),
  path_labels: z.array(z.string()).optional(),
  items: z.array(catalogItemSchema),
});

/** Query envelope folding the caller's row schema into a single validating parse. */
export function datasetQueryResponse<Row extends z.ZodType>(rowSchema: Row) {
  return z.object({
    total_rows: z.number(),
    /** Rows matching the request's filters (ignores limit/offset); absent on older payloads. */
    matched_rows: z.number().optional(),
    returned_rows: z.number(),
    data: z.array(rowSchema),
    /** Human labels for opaque ID columns on this page, keyed by column; absent when none apply. */
    labels: z
      .record(z.string(), z.object({ title: z.string(), values: z.record(z.string(), z.string()) }))
      .optional(),
  });
}

export const datasetQueryResponseSchema = datasetQueryResponse(z.record(z.string(), z.unknown()));

export const catalogStatsSchema = z.object({
  parquet_files: z.number(),
  total_size_mb: z.number(),
  directories: z.record(z.string(), z.number()),
});

export interface CatalogOverviewNode {
  name: string;
  label?: string;
  path: string;
  kind: string;
  parquet_files: number;
  size_mb: number;
  updated_at: string | null;
  children: CatalogOverviewNode[];
}

const catalogOverviewNodeSchema: z.ZodType<CatalogOverviewNode> = z.lazy(() =>
  z.object({
    name: z.string(),
    label: z.string().optional(),
    path: z.string(),
    kind: z.string(),
    parquet_files: z.number(),
    size_mb: z.number(),
    updated_at: z.string().nullable(),
    children: z.array(catalogOverviewNodeSchema),
  }),
);

export const catalogOverviewSchema = z.object({
  summary: z.object({
    parquet_files: z.number(),
    total_size_mb: z.number(),
    updated_at: z.string().nullable(),
  }),
  branches: z.array(catalogOverviewNodeSchema),
});

export type CatalogOverview = z.infer<typeof catalogOverviewSchema>;

const logicalCatalogOptionSchema = z.object({
  resolution: z.string(),
  scope: z.enum(['data', 'features']),
  path: z.string(),
  version: z.string(),
  updated_at: z.string().nullable(),
  // Feature snapshots carry their own description; one item spans several resolutions.
  description: z.string().nullable().optional(),
  exists: z.boolean(),
});

const logicalCatalogItemSchema = z.object({
  id: z.string(),
  kind: z.enum(['dataset', 'feature_set', 'analysis']),
  layer: z.enum(['raw', 'corrected', 'derived', 'features', 'analysis']),
  label: z.string(),
  category_path: z.string(),
  category_labels: z.array(z.string()).optional(),
  description: z.string().nullable(),
  domain: z.string().nullable(),
  status: z.string(),
  asset_column: z.boolean(),
  default_resolution: z.string().nullable(),
  resolutions: z.array(logicalCatalogOptionSchema),
});

const logicalCatalogResponseSchema = z.object({
  items: z.array(logicalCatalogItemSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number().nullable(),
  facets: z.object({
    layers: z.array(z.string()),
    domains: z.array(z.string()),
    groups: z.array(z.string()),
  }),
});

export type CatalogListing = z.infer<typeof catalogListingSchema>;
export type DatasetQueryResponse = z.infer<typeof datasetQueryResponseSchema>;
export type CatalogStats = z.infer<typeof catalogStatsSchema>;

export interface ParquetPreview {
  path: string;
  total_rows: number;
  columns: number;
  schema: { name: string; dtype: string }[];
  page: number;
  page_size: number;
  total_pages: number;
  has_prev: boolean;
  has_next: boolean;
  returned_rows: number;
  rows: Record<string, unknown>[];
}

export interface MarkdownPreview {
  path: string;
  bytes: number;
  lines: number;
  content: string;
}

export interface StructuredPreview {
  path: string;
  bytes: number;
  file_type: string;
  content: unknown;
}

export interface DatasetChartPoint {
  x: string;
  y: number;
}

export type DatasetChartAxis = 'left' | 'right';

export interface DatasetChartBundleSeriesRequest {
  metric: string;
  axis: DatasetChartAxis;
}

export interface DatasetChartBundleCellRequest {
  chart_id: string;
  series: DatasetChartBundleSeriesRequest[];
}

export interface DatasetChartBundleRequest {
  entity_column?: string | null;
  entity_value?: string | null;
  charts: DatasetChartBundleCellRequest[];
  max_points?: number;
}

export interface DatasetChartBundleSeries {
  metric: string;
  axis: DatasetChartAxis;
  label: string;
  isBenchmark?: boolean;
  hideFromLegend?: boolean;
  points_total: number;
  points_returned: number;
  points: DatasetChartPoint[];
}

export interface DatasetChartBundleCell {
  chart_id: string;
  series: DatasetChartBundleSeries[];
}

export interface DatasetChartBundleResponse {
  path: string;
  chartable: boolean;
  reason: string | null;
  x_column: string | null;
  y_columns: string[];
  default_y_column: string | null;
  /** Feature families present among y_columns, in the profile atlas order. */
  families: DatasetFeatureFamily[];
  /** y_column -> family id, for grouping metrics in the chart feature rail. */
  y_column_families: Record<string, string>;
  entity_columns: string[];
  selected_entity_column: string | null;
  selected_entity_value: string | null;
  has_repeated_timestamps: boolean;
  points_total: number;
  points_returned: number;
  downsampled: boolean;
  charts: DatasetChartBundleCell[];
}

export interface DatasetChartValueResponse {
  path: string;
  entity_column: string;
  query: string;
  total_values: number;
  values: string[];
  /** Human labels for opaque values on this page (e.g. UUID → "BTC · Bitcoin"), when configured. */
  labels?: Record<string, string>;
  limit: number;
  offset: number;
}

export type DatasetFeatureRole = 'feature' | 'index' | 'entity';

export interface DatasetFeatureSparkPoint {
  x: string;
  y: number | null;
  p10?: number | null;
  p90?: number | null;
}

export interface DatasetFeatureFamily {
  id: string;
  label: string;
  count: number;
}

export interface DatasetFeatureProfile {
  name: string;
  dtype: string;
  role: DatasetFeatureRole;
  family: string;
  family_label: string;
  non_null_count: number;
  null_count: number;
  coverage: number;
  /** x-axis bounds of the column's non-null rows; null when it never reports. */
  first_non_null: string | null;
  last_non_null: string | null;
  mean: number | null;
  std: number | null;
  min: number | null;
  p25: number | null;
  p50: number | null;
  p75: number | null;
  max: number | null;
  sparkline: DatasetFeatureSparkPoint[];
}

export interface DatasetFeatureProfileResponse {
  path: string;
  total_rows: number;
  total_columns: number;
  feature_columns: number;
  x_column: string | null;
  entity_columns: string[];
  selected_entity_column: string | null;
  selected_entity_value: string | null;
  families: DatasetFeatureFamily[];
  page: number;
  page_size: number;
  total_features: number;
  features: DatasetFeatureProfile[];
}

export interface DatasetFeatureHistogramBin {
  bin_start: number;
  bin_end: number;
  count: number;
}

export interface DatasetFeatureEntityValue {
  entity: string;
  /** Human label for an opaque entity key, when configured. */
  label?: string | null;
  value: number | null;
}

export interface DatasetFeatureProfileDetail {
  path: string;
  column: string;
  dtype: string;
  family: string;
  family_label: string;
  stats: DatasetFeatureProfile;
  sparkline: DatasetFeatureSparkPoint[];
  histogram: DatasetFeatureHistogramBin[];
  latest_timestamp: string | null;
  latest_top: DatasetFeatureEntityValue[];
  latest_bottom: DatasetFeatureEntityValue[];
}

export type DatasetScope = 'data' | 'features';
export type LogicalCatalogKind = 'dataset' | 'feature_set' | 'analysis';
export type LogicalCatalogLayer = 'raw' | 'corrected' | 'derived' | 'features' | 'analysis';
export type LogicalCatalogScope = 'data' | 'features';

export interface LogicalCatalogOption {
  resolution: string;
  scope: LogicalCatalogScope;
  path: string;
  version: string;
  updated_at: string | null;
  description?: string | null;
  exists: boolean;
}

export interface LogicalCatalogItem {
  id: string;
  kind: LogicalCatalogKind;
  layer: LogicalCatalogLayer;
  label: string;
  category_path: string;
  category_labels?: string[];
  description: string | null;
  domain: string | null;
  status: string;
  asset_column: boolean;
  default_resolution: string | null;
  resolutions: LogicalCatalogOption[];
}

export type LogicalCatalogResponse = z.infer<typeof logicalCatalogResponseSchema>;

export interface LogicalCatalogParams {
  kind?: 'dataset' | 'feature_set';
  layer?: 'raw' | 'corrected' | 'derived' | 'features';
  domain?: string | null;
  group?: string | null;
  family?: string | null;
  summary?: boolean;
  q?: string;
  offset?: number;
  limit?: number;
}

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function listCatalog(path = '', signal?: AbortSignal): Promise<CatalogListing> {
  if (path) {
    return requestParsed(`/api/catalog/browse/${encodePath(path)}`, catalogListingSchema, {
      signal,
    });
  }
  return getParsed('/api/catalog', catalogListingSchema, { signal });
}

/** Route prefix for the profile/chart endpoints, which predate the scoped dataset routes. */
const SCOPE_ROUTES: Record<DatasetScope, string> = {
  data: '/api/catalog',
  features: '/api/features',
};

export async function previewDatasetParquet(
  scope: DatasetScope,
  path: string,
  page = 1,
  pageSize = 100,
  signal?: AbortSignal,
): Promise<ParquetPreview> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const encodedPath = encodePath(path);
  const [preview, schema] = await Promise.all([
    requestJson<Omit<ParquetPreview, 'columns' | 'schema'>>(
      `/api/datasets/${scope}/preview/${encodedPath}?${params.toString()}`,
      { signal },
    ),
    requestJson<{ schema: { name: string; dtype: string }[] }>(
      `/api/datasets/${scope}/schema/${encodedPath}`,
      { signal },
    ),
  ]);
  return {
    ...preview,
    columns: schema.schema.length,
    schema: schema.schema,
  };
}

export async function queryDatasetParquet(
  scope: DatasetScope,
  path: string,
  params?: {
    limit?: number;
    offset?: number;
    order_by?: string | null;
    descending?: boolean;
    columns?: string[];
    entity_column?: string | null;
    entity_value?: string | null;
  },
  signal?: AbortSignal,
): Promise<DatasetQueryResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set('limit', String(params.limit));
  if (params?.offset) searchParams.set('offset', String(params.offset));
  if (params?.order_by) searchParams.set('order_by', params.order_by);
  if (params?.descending !== undefined) searchParams.set('descending', String(params.descending));
  if (params?.columns?.length) searchParams.set('columns', params.columns.join(','));
  // Both halves must be present: the endpoint ignores a value without its column.
  if (params?.entity_column && params?.entity_value) {
    searchParams.set('entity_column', params.entity_column);
    searchParams.set('entity_value', params.entity_value);
  }
  const query = searchParams.toString();
  return requestParsed(
    `/api/datasets/${scope}/query/${encodePath(path)}${query ? `?${query}` : ''}`,
    datasetQueryResponseSchema,
    { signal },
  );
}

/** Data-scope alias kept for components that receive scope-bound fetchers. */
export function queryDataParquet(
  path: string,
  params?: Parameters<typeof queryDatasetParquet>[2],
  signal?: AbortSignal,
): Promise<DatasetQueryResponse> {
  return queryDatasetParquet('data', path, params, signal);
}

export async function previewMarkdown(
  path: string,
  signal?: AbortSignal,
): Promise<MarkdownPreview> {
  return requestJson(`/api/catalog/markdown/${encodePath(path)}`, { signal });
}

export async function previewDatasetChartBundle(
  scope: DatasetScope,
  path: string,
  request: DatasetChartBundleRequest,
  signal?: AbortSignal,
): Promise<DatasetChartBundleResponse> {
  return requestJson(`${SCOPE_ROUTES[scope]}/chart-bundle/${encodePath(path)}`, {
    method: 'POST',
    body: request,
    signal,
  });
}

/** Data-scope alias kept for components that receive scope-bound fetchers. */
export function previewChartBundle(
  path: string,
  request: DatasetChartBundleRequest,
  signal?: AbortSignal,
): Promise<DatasetChartBundleResponse> {
  return previewDatasetChartBundle('data', path, request, signal);
}

export async function previewDatasetChartValues(
  scope: DatasetScope,
  path: string,
  params: {
    entity_column: string;
    query?: string;
    limit?: number;
    offset?: number;
  },
  signal?: AbortSignal,
): Promise<DatasetChartValueResponse> {
  const searchParams = new URLSearchParams({ entity_column: params.entity_column });
  if (params.query) searchParams.set('query', params.query);
  if (params.limit) searchParams.set('limit', String(params.limit));
  if (params.offset) searchParams.set('offset', String(params.offset));
  return requestJson(
    `${SCOPE_ROUTES[scope]}/chart-values/${encodePath(path)}?${searchParams.toString()}`,
    { signal },
  );
}

/** Data-scope alias kept for components that receive scope-bound fetchers. */
export function previewChartValues(
  path: string,
  params: Parameters<typeof previewDatasetChartValues>[2],
  signal?: AbortSignal,
): Promise<DatasetChartValueResponse> {
  return previewDatasetChartValues('data', path, params, signal);
}

export async function profileDatasetFeatures(
  scope: DatasetScope,
  path: string,
  params?: {
    preset?: string;
    query?: string;
    family?: string;
    sort?: string;
    page?: number;
    page_size?: number;
    entity_column?: string | null;
    entity_value?: string | null;
    max_spark_points?: number;
  },
  signal?: AbortSignal,
): Promise<DatasetFeatureProfileResponse> {
  const searchParams = new URLSearchParams();
  if (params?.preset) searchParams.set('preset', params.preset);
  if (params?.query) searchParams.set('query', params.query);
  if (params?.family) searchParams.set('family', params.family);
  if (params?.sort) searchParams.set('sort', params.sort);
  if (params?.page) searchParams.set('page', String(params.page));
  if (params?.page_size) searchParams.set('page_size', String(params.page_size));
  if (params?.entity_column) searchParams.set('entity_column', params.entity_column);
  if (params?.entity_value) searchParams.set('entity_value', params.entity_value);
  if (params?.max_spark_points)
    searchParams.set('max_spark_points', String(params.max_spark_points));
  return requestJson(
    `${SCOPE_ROUTES[scope]}/profile/${encodePath(path)}?${searchParams.toString()}`,
    { signal },
  );
}

export async function profileDatasetFeatureDetail(
  scope: DatasetScope,
  path: string,
  params: {
    column: string;
    entity_column?: string | null;
    entity_value?: string | null;
    max_spark_points?: number;
  },
  signal?: AbortSignal,
): Promise<DatasetFeatureProfileDetail> {
  const searchParams = new URLSearchParams({ column: params.column });
  if (params.entity_column) searchParams.set('entity_column', params.entity_column);
  if (params.entity_value) searchParams.set('entity_value', params.entity_value);
  if (params.max_spark_points)
    searchParams.set('max_spark_points', String(params.max_spark_points));
  return requestJson(
    `${SCOPE_ROUTES[scope]}/profile-detail/${encodePath(path)}?${searchParams.toString()}`,
    { signal },
  );
}

export async function getCatalogStats(signal?: AbortSignal): Promise<CatalogStats> {
  return getParsed('/api/catalog/stats', catalogStatsSchema, { signal });
}

/** Size, file count and newest write for each layer, timeframe and provider directory. */
export async function getCatalogOverview(signal?: AbortSignal): Promise<CatalogOverview> {
  return getParsed('/api/catalog/overview', catalogOverviewSchema, { signal });
}

export async function getLogicalCatalog(
  params: LogicalCatalogParams = {},
  signal?: AbortSignal,
): Promise<LogicalCatalogResponse> {
  return getParsed('/api/catalog/logical', logicalCatalogResponseSchema, {
    params: {
      query: {
        kind: params.kind,
        layer: params.layer,
        domain: params.domain,
        group: params.group,
        family: params.family,
        summary: params.summary,
        q: params.q,
        offset: params.offset,
        limit: params.limit,
      },
    },
    signal,
  });
}

/** Largest page the API serves; tree pages walk every page of this size. */
const LOGICAL_CATALOG_PAGE_LIMIT = 1000;

/**
 * Fetch every page of a logical catalog query and merge it into one response.
 * Tree navigators mirror a whole layer, so a single capped page would silently
 * drop whatever sorts last.
 */
export async function getFullLogicalCatalog(
  params: Omit<LogicalCatalogParams, 'offset' | 'limit'> = {},
  signal?: AbortSignal,
): Promise<LogicalCatalogResponse> {
  const first = await getLogicalCatalog(
    { ...params, offset: 0, limit: LOGICAL_CATALOG_PAGE_LIMIT },
    signal,
  );
  const items = [...first.items];
  while (items.length < first.total) {
    const page = await getLogicalCatalog(
      { ...params, offset: items.length, limit: LOGICAL_CATALOG_PAGE_LIMIT },
      signal,
    );
    if (page.items.length === 0) break;
    items.push(...page.items);
  }
  return { ...first, items, offset: 0, limit: null };
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const catalogKeys = {
  all: ['catalog'] as const,
  stats: () => [...catalogKeys.all, 'stats'] as const,
  overview: () => [...catalogKeys.all, 'overview'] as const,
  logical: (params: LogicalCatalogParams = {}) => [...catalogKeys.all, 'logical', params] as const,
  logicalFull: (params: Omit<LogicalCatalogParams, 'offset' | 'limit'> = {}) =>
    [...catalogKeys.all, 'logical-full', params] as const,
};

export function useCatalogStats() {
  return useQuery({
    queryKey: catalogKeys.stats(),
    queryFn: ({ signal }) => getCatalogStats(signal),
    staleTime: STALE.catalog,
  });
}

/** Shared provider names for presentation surfaces without a lake discovery request. */
export function useCatalogLabels() {
  return useQuery({
    queryKey: [...catalogKeys.all, 'labels'],
    queryFn: ({ signal }) =>
      requestParsed('/api/catalog/labels', z.record(z.string(), z.string()), { signal }),
    staleTime: STALE.catalog,
  });
}

export function useCatalogOverview() {
  return useQuery({
    queryKey: catalogKeys.overview(),
    queryFn: ({ signal }) => getCatalogOverview(signal),
    staleTime: STALE.catalog,
  });
}

export function useLogicalCatalog(params: LogicalCatalogParams = {}) {
  return useQuery({
    queryKey: catalogKeys.logical(params),
    queryFn: ({ signal }) => getLogicalCatalog(params, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE.catalog,
  });
}

/** Whole-layer logical catalog for tree navigators (every page, no cap). */
export function useFullLogicalCatalog(
  params: Omit<LogicalCatalogParams, 'offset' | 'limit'> = {},
  enabled = true,
) {
  return useQuery({
    queryKey: catalogKeys.logicalFull(params),
    queryFn: ({ signal }) => getFullLogicalCatalog(params, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE.catalog,
    enabled,
  });
}
