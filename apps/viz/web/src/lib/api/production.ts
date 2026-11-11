/**
 * Production API — read-only live capital telemetry published by `qf-production publish-projection`.
 *
 * USAGE:
 *   const overview = useProductionOverview();             // 404 → isProjectionMissing(error)
 *   const series = useProductionSeries('30d', 'pnl_usd'); // aggregate + per-strategy lines
 *   const strategy = useProductionStrategy('family-a');
 *   const line = useProductionStrategySeries('family-a', '30d', 'equity');
 *
 * The schemas mirror the response models in `apps/api/src/db_api/routers/production.py`
 * field for field; `null` means unsupportable, never zero.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed } from './client';
import { ApiError } from './errors';
import { REFRESH_LIVE_FEED, STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export const PRODUCTION_RANGES = ['1d', '7d', '30d', 'ytd', 'all'] as const;
export const PRODUCTION_METRICS = ['pnl_usd', 'return_pct', 'equity'] as const;

export type ProductionRange = (typeof PRODUCTION_RANGES)[number];
export type ProductionMetric = (typeof PRODUCTION_METRICS)[number];

const health = z.enum(['healthy', 'attention', 'unknown', 'paused']);

export const productionMetricsSchema = z.object({
  total_pnl_usd: z.number().nullable(),
  total_return: z.number().nullable(),
  max_drawdown: z.number().nullable(),
  annualized_volatility: z.number().nullable(),
  sharpe: z.number().nullable(),
  positive_day_rate: z.number().nullable(),
  observation_count: z.number().int().nonnegative(),
});

export const productionMemberSchema = z.object({
  family: z.string(),
  included: z.boolean(),
  state: z.string().nullable(),
  health,
  stale: z.boolean(),
  capital_weight: z.number().nullable(),
  equity_usd: z.number().nullable(),
  inception_pnl_usd: z.number().nullable(),
  period_pnl_usd: z.number().nullable(),
  last_observation_at: z.string().nullable(),
});

export const productionOverviewSchema = z.object({
  schema_version: z.literal(1),
  portfolio_id: z.string(),
  generated_at: z.string(),
  completeness: z.enum(['complete', 'incomplete', 'stale', 'empty']),
  equity_usd: z.number().nullable(),
  today_pnl_usd: z.number().nullable(),
  inception_pnl_usd: z.number().nullable(),
  missing_families: z.array(z.string()),
  stale_families: z.array(z.string()),
  included_families: z.array(z.string()),
  metrics: productionMetricsSchema,
  members: z.array(productionMemberSchema),
});

export const productionSeriesPointSchema = z.object({
  day: z.string(),
  value: z.number().nullable(),
  complete: z.boolean(),
});

export const productionSeriesLineSchema = z.object({
  family: z.string().nullable(),
  points: z.array(productionSeriesPointSchema),
});

export const productionSeriesSchema = z.object({
  range: z.enum(PRODUCTION_RANGES),
  metric: z.enum(PRODUCTION_METRICS),
  portfolio_id: z.string(),
  generated_at: z.string(),
  complete: z.boolean(),
  aggregate: productionSeriesLineSchema,
  strategies: z.array(productionSeriesLineSchema),
});

export const productionPositionSchema = z.object({
  instrument: z.string(),
  side: z.enum(['LONG', 'SHORT']),
  quantity: z.number(),
  contracts: z.number().int().nullable(),
  current_price: z.number(),
  entry_price: z.number(),
  market_value_usd: z.number(),
  unrealized_pnl_usd: z.number(),
  daily_realized_pnl_usd: z.number().nullable(),
});

export const productionCapitalSchema = z.object({
  as_of: z.string(),
  equity_usd: z.number(),
  cash_usd: z.number().nullable(),
  gross_exposure_usd: z.number().nullable(),
  net_exposure_usd: z.number().nullable(),
  realized_pnl_usd: z.number().nullable(),
  unrealized_pnl_usd: z.number().nullable(),
  fees_usd: z.number().nullable(),
  funding_pnl_usd: z.number().nullable(),
  capital_weight: z.number().nullable(),
  positions: z.array(productionPositionSchema),
});

export const productionDeploymentSchema = z.object({
  family: z.string(),
  memory_version: z.string(),
  preset: z.string(),
  venue: z.string(),
  instrument: z.string(),
  account_alias: z.string(),
  host_alias: z.string(),
  host_region: z.string(),
  schedule: z.string(),
  timezone: z.string(),
  host_git_sha: z.string(),
  deployment_fingerprint: z.string(),
});

export const productionAuthoritySchema = z.object({
  activation_state: z.enum(['missing', 'disabled', 'expired', 'wrong-schema', 'enabled']),
  activation_expires_at: z.string().nullable(),
  armed: z.boolean(),
  venue_gate: z.enum(['open', 'closed', 'n/a']),
  capital_gate: z.enum(['open', 'closed', 'n/a']),
  deactivated: z.boolean(),
  can_trade: z.boolean(),
  scheduled: z.boolean(),
  autonomous_live: z.boolean(),
});

export const productionHealthCheckSchema = z.object({
  name: z.enum([
    'deployment_identity',
    'scheduler',
    'pipeline',
    'input_freshness',
    'execution',
    'account_snapshot',
    'reconciliation',
  ]),
  state: z.enum(['passing', 'failing', 'unknown']),
  detail: z.string(),
});

export const productionLastRunSchema = z.object({
  result: z.enum(['never', 'success', 'failure']),
  at: z.string().nullable(),
  mode: z.enum(['dry-run', 'live']).nullable(),
  journal_at: z.string().nullable(),
});

export const productionStrategySchema = z.object({
  schema_version: z.literal(1),
  portfolio_id: z.string(),
  generated_at: z.string(),
  family: z.string(),
  included: z.boolean(),
  state: z.string(),
  health,
  stale: z.boolean(),
  max_age_seconds: z.number().int().positive(),
  last_observation_at: z.string().nullable(),
  today_pnl_usd: z.number().nullable(),
  inception_pnl_usd: z.number().nullable(),
  deployment: productionDeploymentSchema,
  authority_facts: productionAuthoritySchema,
  health_checks: z.array(productionHealthCheckSchema),
  last_run: productionLastRunSchema,
  capital: productionCapitalSchema.nullable(),
  metrics: productionMetricsSchema,
});

export type ProductionMetrics = z.infer<typeof productionMetricsSchema>;
export type ProductionMember = z.infer<typeof productionMemberSchema>;
export type ProductionOverview = z.infer<typeof productionOverviewSchema>;
export type ProductionSeries = z.infer<typeof productionSeriesSchema>;
export type ProductionSeriesLine = z.infer<typeof productionSeriesLineSchema>;
export type ProductionStrategy = z.infer<typeof productionStrategySchema>;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** True when nothing is published under `db/production` yet (the API answers 404). */
export function isProjectionMissing(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const productionKeys = {
  all: ['production'] as const,
  overview: () => [...productionKeys.all, 'overview'] as const,
  series: (range: ProductionRange, metric: ProductionMetric) =>
    [...productionKeys.all, 'series', range, metric] as const,
  strategy: (family: string) => [...productionKeys.all, 'strategy', family] as const,
  strategySeries: (family: string, range: ProductionRange, metric: ProductionMetric) =>
    [...productionKeys.all, 'strategy-series', family, range, metric] as const,
};

export function useProductionOverview() {
  return useQuery({
    queryKey: productionKeys.overview(),
    queryFn: ({ signal }) =>
      getParsed('/api/production/overview', productionOverviewSchema, { signal }),
    staleTime: STALE.liveFeed,
    refetchInterval: REFRESH_LIVE_FEED,
  });
}

export function useProductionSeries(
  range: ProductionRange,
  metric: ProductionMetric,
  enabled = true,
) {
  return useQuery({
    queryKey: productionKeys.series(range, metric),
    queryFn: ({ signal }) =>
      getParsed('/api/production/series', productionSeriesSchema, {
        params: { query: { range, metric } },
        signal,
      }),
    staleTime: STALE.liveFeed,
    refetchInterval: REFRESH_LIVE_FEED,
    enabled,
  });
}

export function useProductionStrategy(family: string) {
  return useQuery({
    queryKey: productionKeys.strategy(family),
    queryFn: ({ signal }) =>
      getParsed('/api/production/strategies/{family}', productionStrategySchema, {
        params: { path: { family } },
        signal,
      }),
    staleTime: STALE.liveFeed,
    refetchInterval: REFRESH_LIVE_FEED,
    enabled: Boolean(family),
  });
}

export function useProductionStrategySeries(
  family: string,
  range: ProductionRange,
  metric: ProductionMetric,
) {
  return useQuery({
    queryKey: productionKeys.strategySeries(family, range, metric),
    queryFn: ({ signal }) =>
      getParsed('/api/production/strategies/{family}/series', productionSeriesSchema, {
        params: { path: { family }, query: { range, metric } },
        signal,
      }),
    staleTime: STALE.liveFeed,
    refetchInterval: REFRESH_LIVE_FEED,
    enabled: Boolean(family),
  });
}
