/**
 * Features API — feature browser, analysis artifacts, feature-scope fetch aliases.
 *
 * USAGE:
 *   const { data } = useFeatureBrowserStats();
 *   const { data: analysis } = useFeatureAnalysisCorrelation(path);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';

import type {
  CatalogListing,
  CatalogStats,
  DatasetChartBundleRequest,
  DatasetChartBundleResponse,
  DatasetChartValueResponse,
  DatasetQueryResponse,
  MarkdownPreview,
  StructuredPreview,
} from './catalog';
import {
  catalogListingSchema,
  catalogStatsSchema,
  previewDatasetChartBundle,
  previewDatasetChartValues,
  queryDatasetParquet,
} from './catalog';
import { getParsed, requestJson, requestParsed } from './client';
import { encodePath } from './paths';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema / types
// --------------------------------------------------------------------------- #

export interface FeatureAnalysisCorrelation {
  path: string;
  total_rows: number;
  returned_cells: number;
  dimension: number;
  feature_count: number;
  clusters: number;
  representatives: number;
  representatives_only: boolean;
  row_index: number[];
  column_index: number[];
  correlation: (number | null)[];
  distribution: {
    key: string;
    label: string;
    count: number;
    share: number;
  }[];
  top_pairs: {
    row_feature: string;
    column_feature: string;
    correlation: number;
    abs_correlation: number;
    row_cluster_id: number;
    column_cluster_id: number;
  }[];
}

export interface FeatureAnalysisIc {
  path: string;
  total_rows: number;
  total_features: number;
  features: string[];
  horizons: number[];
  feature_index: number[];
  horizon: number[];
  mean_oriented_ic: (number | null)[];
  mean_validation_ic: (number | null)[];
  positive_fold_rate: (number | null)[];
  valid_folds: (number | null)[];
}

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function browseFeatureFiles(path = '', signal?: AbortSignal): Promise<CatalogListing> {
  if (path) {
    return requestParsed(`/api/features/browser/${encodePath(path)}`, catalogListingSchema, {
      signal,
    });
  }
  return getParsed('/api/features/browser', catalogListingSchema, { signal });
}

/** Features-scope alias kept for components that receive scope-bound fetchers. */
export function queryFeatureParquet(
  path: string,
  params?: Parameters<typeof queryDatasetParquet>[2],
  signal?: AbortSignal,
): Promise<DatasetQueryResponse> {
  return queryDatasetParquet('features', path, params, signal);
}

export async function getFeatureAnalysisCorrelation(
  path: string,
  signal?: AbortSignal,
): Promise<FeatureAnalysisCorrelation> {
  return requestJson(`/api/features/analysis/correlation/${encodePath(path)}`, { signal });
}

export async function getFeatureAnalysisIc(
  path: string,
  signal?: AbortSignal,
): Promise<FeatureAnalysisIc> {
  return requestJson(`/api/features/analysis/ic/${encodePath(path)}`, { signal });
}

export async function previewFeatureMarkdown(
  path: string,
  signal?: AbortSignal,
): Promise<MarkdownPreview> {
  return requestJson(`/api/features/markdown/${encodePath(path)}`, { signal });
}

export async function previewFeatureStructured(
  path: string,
  signal?: AbortSignal,
): Promise<StructuredPreview> {
  return requestJson(`/api/features/structured/${encodePath(path)}`, { signal });
}

/** Features-scope alias kept for components that receive scope-bound fetchers. */
export function previewFeatureChartBundle(
  path: string,
  request: DatasetChartBundleRequest,
  signal?: AbortSignal,
): Promise<DatasetChartBundleResponse> {
  return previewDatasetChartBundle('features', path, request, signal);
}

/** Features-scope alias kept for components that receive scope-bound fetchers. */
export function previewFeatureChartValues(
  path: string,
  params: Parameters<typeof previewDatasetChartValues>[2],
  signal?: AbortSignal,
): Promise<DatasetChartValueResponse> {
  return previewDatasetChartValues('features', path, params, signal);
}

export async function getFeatureBrowserStats(signal?: AbortSignal): Promise<CatalogStats> {
  return getParsed('/api/features/browser-stats', catalogStatsSchema, { signal });
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const featureKeys = {
  all: ['features'] as const,
  browser: (path = '') => [...featureKeys.all, 'browser', path] as const,
  browserStats: () => [...featureKeys.all, 'browser-stats'] as const,
  analysisCorrelation: (path: string) =>
    [...featureKeys.all, 'analysis-correlation', path] as const,
  analysisIc: (path: string) => [...featureKeys.all, 'analysis-ic', path] as const,
};

export function useFeatureBrowserStats() {
  return useQuery({
    queryKey: featureKeys.browserStats(),
    queryFn: ({ signal }) => getFeatureBrowserStats(signal),
    staleTime: STALE.catalog,
  });
}

export function useFeatureAnalysisCorrelation(path: string) {
  return useQuery({
    queryKey: featureKeys.analysisCorrelation(path),
    queryFn: ({ signal }) => getFeatureAnalysisCorrelation(path, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(path),
  });
}

export function useFeatureAnalysisIc(path: string) {
  return useQuery({
    queryKey: featureKeys.analysisIc(path),
    queryFn: ({ signal }) => getFeatureAnalysisIc(path, signal),
    staleTime: STALE.analysis,
    enabled: Boolean(path),
  });
}
