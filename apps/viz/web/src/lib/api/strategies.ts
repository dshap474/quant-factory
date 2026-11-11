/**
 * Strategies API — types, versions, runs, leaders, research surfaces.
 *
 * USAGE:
 *   const { data } = useStrategyTypes();
 *   const surface = await getVersionSurface(type, version);
 *
 * Response shapes from OpenAPI are loose; list endpoints are normalized, and
 * research surfaces are Zod-validated at the trust boundary.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { getParsed, openapiGet } from './client';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Types + schemas
// --------------------------------------------------------------------------- #

export interface StrategyTypeSummary {
  strategy_type: string;
  description: string;
  total_runs: number;
  version_count: number;
  versions: string[];
  best_sharpe: number | null;
  latest_run: string | null;
}

export interface StrategyVersionSummary {
  memory_version: string;
  run_count: number;
  best_sharpe: number | null;
  best_return: number | null;
  latest_run: string | null;
  final_run_id: string | null;
  state: 'candidate' | 'rejected' | 'invalidated' | 'promoted';
  display_state: 'baseline' | 'candidate' | 'rejected' | 'invalidated' | 'promoted';
  source: 'research' | 'canonical';
  selected_run_id: string | null;
  experiment: string | null;
  has_surface: boolean;
  lifecycle_phase: string | null;
  lifecycle_status: string | null;
  invalidation_reason: string | null;
  scored_observations: number | null;
}

export interface VersionRunSummary {
  strategy_type: string;
  memory_version: string;
  run_id: string;
  preset?: string | null;
  metrics: Record<string, number>;
  config: Record<string, unknown>;
  created_at: string | null;
  data_range: { start: string; end: string } | null;
  is_final?: boolean;
}

/** Single backtest run payload shape. */
export interface BacktestDetail {
  strategy_id: string;
  run_id: string;
  metrics: Record<string, number | null>;
  config: Record<string, unknown>;
  created_at: string | null;
  data_range: { start: string; end: string } | null;
  data: Record<string, unknown>[];
  columns: string[];
}

/** The operator-promoted run for one memory version. */
export interface VersionFinal extends BacktestDetail {
  strategy_type?: string;
  memory_version?: string;
  selected_run_id?: string | null;
}

const nullableNumber = z.number().nullable();

// Unknown published metrics pass through for extension-contributed comparison rows.
const standardMetricsSchema = z.looseObject({
  total_return: z.number(),
  sharpe: nullableNumber,
  max_drawdown: z.number(),
  ending_value: z.number(),
  annualized_return: nullableNumber,
  annualized_volatility: z.number(),
  calmar: nullableNumber,
  sortino: nullableNumber.optional(),
  martin: nullableNumber.optional(),
  longest_drawdown_days: nullableNumber.optional(),
  current_drawdown_days: nullableNumber.optional(),
  positive_days: z.number(),
});

const surfaceRowSchema = z.looseObject({
  date: z.string(),
  strategy_daily_return: z.number(),
  strategy_portfolio_value: z.number(),
  benchmark_daily_return: z.number(),
  benchmark_portfolio_value: z.number(),
});

const pnlRowSchema = z.object({
  timestamp: z.string(),
  cumulative_pnl_usd: z.number(),
  benchmark_cumulative_pnl_usd: z.number().optional(),
});

const pnlMetadataSchema = z.object({
  path: z.string(),
  columns: z.union([
    z.tuple([z.literal('timestamp'), z.literal('cumulative_pnl_usd')]),
    z.tuple([
      z.literal('timestamp'),
      z.literal('cumulative_pnl_usd'),
      z.literal('benchmark_cumulative_pnl_usd'),
    ]),
  ]),
  row_count: z.number().int().positive(),
  label: z.string().min(1),
  allocation_usd: z.number().positive(),
  interpretation: z.enum(['backtest', 'protocol_stop']),
});

const gridDimensionSchema = z.union([
  z.object({
    key: z.string(),
    label: z.string(),
    format: z.enum(['bps', 'number', 'percent']),
    values: z.array(z.number()),
  }),
  z.object({
    key: z.string(),
    label: z.string(),
    format: z.literal('text'),
    values: z.array(z.string()),
  }),
]);

const gridMetricSchema = z.object({
  key: z.string(),
  label: z.string(),
  format: z.enum(['number', 'percent']),
  higher_is_better: z.boolean(),
});

const gridFileSchema = z.object({
  path: z.string(),
  row_count: z.number(),
});

const gridMetadataSchema = z.object({
  grid_schema_version: z.literal(1),
  dimensions: z.array(gridDimensionSchema).min(2),
  metrics: z.array(gridMetricSchema).min(1),
  selected_config_id: z.string(),
  control_config_id: z.string(),
  summary: gridFileSchema.extend({ columns: z.array(z.string()) }),
  series: gridFileSchema.extend({
    config_id_column: z.string(),
    date_column: z.string(),
    return_column: z.string(),
  }),
});

const gridRowSchema = z.looseObject({
  rank: z.number(),
  config_id: z.string(),
  is_selected: z.boolean(),
  is_control: z.boolean(),
});

// Null cells are dates outside that role's observed coverage (or display breaks), never zero returns.
const gridComparisonRowSchema = z.object({
  date: z.string(),
  selected_daily_return: z.number().nullable(),
  selected_portfolio_value: z.number().nullable(),
  control_daily_return: z.number().nullable(),
  control_portfolio_value: z.number().nullable(),
  benchmark_daily_return: z.number().nullable(),
  benchmark_portfolio_value: z.number().nullable(),
});

const gridRoleCoverageSchema = z.object({
  observed_days: z.number().int().nonnegative(),
  first_date: z.string().nullable(),
  last_date: z.string().nullable(),
});

/** A supplement that compares named variants of the selected run on the surface's sampled dates. */
const variantMatrixSchema = z.object({
  run_id: z.string(),
  title: z.string().optional(),
  variants: z
    .array(
      z.object({
        id: z.string(),
        label: z.string(),
        metrics: standardMetricsSchema,
        gross_return: z.number().optional(),
        gross_sharpe: z.number().optional(),
        data: z.array(
          z.object({
            date: z.string(),
            daily_return: z.number(),
            portfolio_value: z.number(),
          }),
        ),
      }),
    )
    .min(1),
});

export type VariantMatrix = z.infer<typeof variantMatrixSchema>;

/** The supplements shaped as variant matrices; supplements of any other shape are not rendered. */
function variantMatrices(supplements: Record<string, unknown> | undefined) {
  return Object.fromEntries(
    Object.entries(supplements ?? {}).flatMap(([label, value]) => {
      const parsed = variantMatrixSchema.safeParse(value);
      return parsed.success ? [[label, parsed.data] as const] : [];
    }),
  );
}

export const researchSurfaceSchema = z
  .object({
    schema_version: z.literal(1),
    strategy_type: z.string(),
    memory_version: z.string(),
    state: z.enum(['candidate', 'rejected']),
    display_state: z.enum(['baseline', 'candidate', 'rejected']).optional(),
    operator_baseline: z.boolean().optional(),
    experiment: z.string(),
    run_id: z.string(),
    published_at: z.string(),
    title: z.string(),
    summary: z.string(),
    benchmark: z.object({ id: z.string(), label: z.string() }).nullable(),
    performance_unit: z.enum(['usd', 'index']).nullable().optional(),
    pnl: pnlMetadataSchema.nullable().optional(),
    metrics: z
      .object({
        strategy: standardMetricsSchema,
        benchmark: standardMetricsSchema,
      })
      .nullable(),
    comparison: z
      .object({
        id: z.string(),
        label: z.string(),
        run_id: z.string(),
        metrics: standardMetricsSchema,
        points_total: z.number().int().positive(),
        points_returned: z.number().int().positive(),
        data: z.array(
          z.object({
            date: z.string(),
            daily_return: z.number(),
            portfolio_value: z.number(),
          }),
        ),
      })
      .nullable()
      .optional(),
    comparison_issue: z.string().nullable().optional(),
    /** Extension-loaded run artifacts keyed by manifest provenance label. */
    supplements: z.record(z.string(), z.unknown()).optional(),
    diagnostics: z.array(
      z.object({
        key: z.string(),
        label: z.string(),
        value: z.union([z.number(), z.string()]),
        format: z.enum(['number', 'percent', 'money', 'text']),
      }),
    ),
    gates: z.array(
      z.object({
        name: z.string(),
        requirement: z.string(),
        result: z.union([z.number(), z.string(), z.null()]),
        format: z.enum(['number', 'percent', 'money', 'text']),
        passed: z.boolean(),
      }),
    ),
    disclosures: z.array(z.string()),
    grid: gridMetadataSchema.optional(),
    points_total: z.number().int().nonnegative().optional(),
    points_returned: z.number().int().nonnegative().optional(),
    downsampled: z.boolean().optional(),
    data: z.array(z.union([surfaceRowSchema, pnlRowSchema])),
  })
  .superRefine((surface, context) => {
    if (
      surface.comparison &&
      (surface.comparison.run_id !== surface.run_id ||
        surface.comparison.points_total !== (surface.points_total ?? surface.data.length) ||
        surface.comparison.points_returned !== surface.comparison.data.length ||
        surface.comparison.data.length !== surface.data.length ||
        surface.comparison.data.some(
          (row, index) => row.date !== (surface.data[index] as { date?: string })?.date,
        ))
    ) {
      context.addIssue({
        code: 'custom',
        message: 'comparison must match the selected run and sampled dates',
      });
    }
    for (const [label, matrix] of Object.entries(variantMatrices(surface.supplements))) {
      if (
        matrix.run_id !== surface.run_id ||
        matrix.variants.some(
          (variant) =>
            variant.data.length !== surface.data.length ||
            variant.data.some(
              (row, index) => row.date !== (surface.data[index] as { date?: string })?.date,
            ),
        )
      ) {
        context.addIssue({
          code: 'custom',
          message: `${label} must match the selected run and sampled dates`,
        });
      }
    }
    const pointsTotal = surface.points_total ?? surface.data.length;
    const pointsReturned = surface.points_returned ?? surface.data.length;
    const downsampled = surface.downsampled ?? false;
    const performanceRows = surface.data.every((row) => 'date' in row);
    const pnlRows = surface.data.every((row) => 'timestamp' in row);
    const hasPerformanceUnit = surface.performance_unit != null;
    const sampleIsConsistent =
      surface.data.length === pointsReturned &&
      pointsReturned <= pointsTotal &&
      downsampled === pointsReturned < pointsTotal;
    const completePerformance =
      surface.benchmark !== null &&
      surface.metrics !== null &&
      surface.pnl == null &&
      surface.data.length > 0 &&
      sampleIsConsistent &&
      performanceRows;
    const pnlHasBenchmark = surface.pnl?.columns.length === 3;
    const pnlRowsHaveBenchmark = surface.data.every(
      (row) => 'timestamp' in row && row.benchmark_cumulative_pnl_usd !== undefined,
    );
    const pnlBenchmarkIsComplete = pnlHasBenchmark
      ? surface.benchmark !== null && pnlRowsHaveBenchmark
      : surface.benchmark === null;
    const pnlRecord =
      pnlBenchmarkIsComplete &&
      surface.metrics === null &&
      surface.pnl != null &&
      !hasPerformanceUnit &&
      surface.data.length > 0 &&
      pointsTotal === surface.pnl.row_count &&
      sampleIsConsistent &&
      pnlRows;
    const textOnlyRecord =
      surface.benchmark === null &&
      surface.metrics === null &&
      surface.pnl == null &&
      !hasPerformanceUnit &&
      surface.data.length === 0 &&
      pointsTotal === 0 &&
      pointsReturned === 0 &&
      !downsampled &&
      surface.grid === undefined;
    if (!completePerformance && !pnlRecord && !textOnlyRecord) {
      context.addIssue({
        code: 'custom',
        message: 'research surface must contain complete performance, PnL, or a text-only record',
      });
    }
  })
  .transform((surface) => ({
    ...surface,
    performance_unit: surface.performance_unit ?? (surface.metrics ? 'usd' : null),
    display_state: surface.display_state ?? surface.state,
    points_total: surface.points_total ?? surface.data.length,
    points_returned: surface.points_returned ?? surface.data.length,
    downsampled: surface.downsampled ?? false,
    variant_matrices: Object.values(variantMatrices(surface.supplements)),
  }));

export type ResearchStrategySurface = z.infer<typeof researchSurfaceSchema>;
export const researchGridSchema = gridMetadataSchema.extend({
  columns: z.array(z.string()),
  data: z.array(gridRowSchema),
});
export type ResearchGrid = z.infer<typeof researchGridSchema>;

export const researchGridConfigurationSchema = z.object({
  config: gridRowSchema,
  control: gridRowSchema,
  benchmark: z.object({ id: z.string(), label: z.string() }),
  metrics: z.object({
    selected: standardMetricsSchema,
    control: standardMetricsSchema,
    benchmark: standardMetricsSchema.nullable(),
  }),
  coverage: z
    .object({
      calendar_days: z.number().int().nonnegative(),
      selected: gridRoleCoverageSchema,
      control: gridRoleCoverageSchema,
      benchmark: gridRoleCoverageSchema,
    })
    .optional(),
  columns: z.array(z.string()),
  data: z.array(gridComparisonRowSchema),
});
export type ResearchGridConfiguration = z.infer<typeof researchGridConfigurationSchema>;

const metricDirectionSchema = z.enum(['higher', 'lower', 'unranked']);
const rankValuesSchema = z.record(z.string(), z.number().nullable());
const rankCellSchema = z.object({
  rank: z.number().int().positive(),
  count: z.number().int().positive(),
  ties: z.number().int().nonnegative(),
  position: z.number().min(0).max(1).nullable(),
  value: z.number(),
});

export const versionRankSchema = z.object({
  strategy_type: z.string(),
  memory_version: z.string(),
  label: z.string(),
  conventions: z.string(),
  metrics: z.array(
    z.object({ key: z.string(), aliases: z.array(z.string()), direction: metricDirectionSchema }),
  ),
  window: z
    .object({
      start_mark: z.string(),
      first_return: z.string(),
      end: z.string(),
      observations: z.number().int(),
    })
    .nullable(),
  unavailable_reason: z.string().nullable(),
  peers: z.array(
    z.object({
      memory_version: z.string(),
      display_state: z.string(),
      source: z.enum(['selected_configuration', 'strategy']),
      config_id: z.string().nullable(),
      values: rankValuesSchema,
    }),
  ),
  excluded: z.array(
    z.object({ memory_version: z.string(), reason: z.string(), detail: z.string() }),
  ),
  columns: z.array(
    z.object({
      config_id: z.string(),
      values: rankValuesSchema,
      ranks: z.record(z.string(), rankCellSchema.nullable()),
    }),
  ),
});
export type VersionRank = z.infer<typeof versionRankSchema>;

const singleAssetRowSchema = z.object({
  timestamp: z.string(),
  price: z.number().positive().nullable(),
  // Null only on display break rows that mark skipped calendar days.
  weight_percent: z.number().nullable(),
  cumulative_contribution_pp: z.number().nullable(),
});

const singleAssetRankingSchema = z.object({
  asset: z.string(),
  net_contribution_pp: z.number(),
  mean_abs_weight_percent: z.number().nonnegative(),
  peak_abs_weight_percent: z.number().nonnegative(),
  held_percent: z.number().min(0).max(100),
});
export type SingleAssetRanking = z.infer<typeof singleAssetRankingSchema>;

export const singleAssetViewSchema = z.discriminatedUnion('available', [
  z.object({
    available: z.literal(true),
    reason: z.null(),
    strategy_type: z.string(),
    memory_version: z.string(),
    run_id: z.string(),
    experiment: z.string(),
    title: z.string(),
    artifact_contract: z.enum(['ordinary_ledger_v1', 'asset_attribution_v1']),
    config_id: z.string().optional(),
    configurations: z
      .array(
        z.object({
          id: z.string(),
          label: z.string(),
          cost_bps: z.number().nonnegative().optional(),
        }),
      )
      .optional(),
    asset: z.string(),
    assets: z.array(z.string()).min(1),
    cost_bps: z.number().nonnegative(),
    rebalance_every_bars: z.number().int().positive().nullable(),
    points_total: z.number().int().positive(),
    points_returned: z.number().int().positive(),
    downsampled: z.boolean(),
    first_observed_at: z.string().nullable(),
    last_observed_at: z.string().nullable(),
    ever_held: z.boolean(),
    peak_abs_weight_percent: z.number().nonnegative(),
    ending_contribution_pp: z.number(),
    ranking: z.array(singleAssetRankingSchema).optional(),
    capital_basis: z.enum(['actual_holdings', 'rebased_windows']).optional(),
    methodology: z.string(),
    data: z.array(singleAssetRowSchema).min(1),
  }),
  z.object({
    available: z.literal(false),
    reason: z.string().min(1),
    strategy_type: z.string(),
    memory_version: z.string(),
    run_id: z.string().nullable(),
    asset: z.null(),
    assets: z.array(z.string()).length(0),
    data: z.array(singleAssetRowSchema).length(0),
  }),
]);

export type SingleAssetView = z.infer<typeof singleAssetViewSchema>;

// --------------------------------------------------------------------------- #
// Normalizers
// --------------------------------------------------------------------------- #

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

export function normalizeStrategyTypeSummary(item: unknown): StrategyTypeSummary {
  const source = (item ?? {}) as Record<string, unknown>;
  return {
    strategy_type: String(source.strategy_type ?? ''),
    description: typeof source.description === 'string' ? source.description : '',
    total_runs: typeof source.total_runs === 'number' ? source.total_runs : 0,
    version_count: typeof source.version_count === 'number' ? source.version_count : 0,
    versions: asStringArray(source.versions),
    best_sharpe: typeof source.best_sharpe === 'number' ? source.best_sharpe : null,
    latest_run: typeof source.latest_run === 'string' ? source.latest_run : null,
  };
}

export function normalizeVersionSummary(item: unknown): StrategyVersionSummary {
  if (typeof item === 'string') {
    return {
      memory_version: item,
      run_count: 0,
      best_sharpe: null,
      best_return: null,
      latest_run: null,
      final_run_id: null,
      state: 'promoted',
      display_state: 'promoted',
      source: 'canonical',
      selected_run_id: null,
      experiment: null,
      has_surface: false,
      lifecycle_phase: null,
      lifecycle_status: null,
      invalidation_reason: null,
      scored_observations: null,
    };
  }

  const source = (item ?? {}) as Record<string, unknown>;
  return {
    memory_version: String(source.memory_version ?? ''),
    run_count:
      typeof source.run_count === 'number'
        ? source.run_count
        : typeof source.total_runs === 'number'
          ? source.total_runs
          : 0,
    best_sharpe: typeof source.best_sharpe === 'number' ? source.best_sharpe : null,
    best_return: typeof source.best_return === 'number' ? source.best_return : null,
    latest_run: typeof source.latest_run === 'string' ? source.latest_run : null,
    final_run_id:
      typeof source.final_run_id === 'string'
        ? source.final_run_id
        : typeof source.run_id === 'string'
          ? source.run_id
          : null,
    state:
      source.state === 'candidate' || source.state === 'rejected' || source.state === 'invalidated'
        ? source.state
        : 'promoted',
    display_state:
      source.display_state === 'baseline' ||
      source.display_state === 'candidate' ||
      source.display_state === 'rejected' ||
      source.display_state === 'invalidated'
        ? source.display_state
        : source.state === 'candidate' ||
            source.state === 'rejected' ||
            source.state === 'invalidated'
          ? source.state
          : 'promoted',
    source: source.source === 'research' ? 'research' : 'canonical',
    selected_run_id: typeof source.selected_run_id === 'string' ? source.selected_run_id : null,
    experiment: typeof source.experiment === 'string' ? source.experiment : null,
    has_surface: source.has_surface === true,
    lifecycle_phase: typeof source.lifecycle_phase === 'string' ? source.lifecycle_phase : null,
    lifecycle_status: typeof source.lifecycle_status === 'string' ? source.lifecycle_status : null,
    invalidation_reason:
      typeof source.invalidation_reason === 'string' ? source.invalidation_reason : null,
    scored_observations:
      typeof source.scored_observations === 'number' ? source.scored_observations : null,
  };
}

export function normalizeVersionRun(item: unknown): VersionRunSummary {
  const source = (item ?? {}) as Record<string, unknown>;
  const config =
    source.config && typeof source.config === 'object'
      ? (source.config as Record<string, unknown>)
      : typeof source.config_json === 'string'
        ? (() => {
            try {
              return JSON.parse(source.config_json) as Record<string, unknown>;
            } catch {
              return {};
            }
          })()
        : {};
  const metrics =
    source.metrics && typeof source.metrics === 'object'
      ? (source.metrics as Record<string, number>)
      : {
          total_return: typeof source.total_return === 'number' ? source.total_return : Number.NaN,
          ann_return: typeof source.ann_return === 'number' ? source.ann_return : Number.NaN,
          ann_vol: typeof source.ann_vol === 'number' ? source.ann_vol : Number.NaN,
          sharpe: typeof source.sharpe === 'number' ? source.sharpe : Number.NaN,
          sortino: typeof source.sortino === 'number' ? source.sortino : Number.NaN,
          martin: typeof source.martin === 'number' ? source.martin : Number.NaN,
          max_drawdown: typeof source.max_drawdown === 'number' ? source.max_drawdown : Number.NaN,
          calmar: typeof source.calmar === 'number' ? source.calmar : Number.NaN,
          avg_turnover: typeof source.avg_turnover === 'number' ? source.avg_turnover : Number.NaN,
          funding_share:
            typeof source.funding_share === 'number' ? source.funding_share : Number.NaN,
          win_rate: typeof source.win_rate === 'number' ? source.win_rate : Number.NaN,
        };
  return {
    strategy_type: String(source.strategy_type ?? ''),
    memory_version: String(source.memory_version ?? ''),
    run_id: String(source.run_id ?? ''),
    preset: typeof source.preset === 'string' ? source.preset : null,
    metrics: Object.fromEntries(
      Object.entries(metrics).filter(
        ([, value]) => typeof value === 'number' && Number.isFinite(value),
      ),
    ),
    config,
    created_at: typeof source.created_at === 'string' ? source.created_at : null,
    data_range:
      source.data_range && typeof source.data_range === 'object'
        ? (source.data_range as { start: string; end: string })
        : typeof source.data_start === 'string' && typeof source.data_end === 'string'
          ? { start: source.data_start, end: source.data_end }
          : null,
    is_final: typeof source.is_final === 'boolean' ? source.is_final : false,
  };
}

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function listStrategyTypes(signal?: AbortSignal): Promise<StrategyTypeSummary[]> {
  const data = await getParsed('/api/backtests/strategy-types', z.array(z.unknown()), { signal });
  return data.map(normalizeStrategyTypeSummary);
}

export async function listStrategyVersions(
  strategyType: string,
  signal?: AbortSignal,
): Promise<StrategyVersionSummary[]> {
  const data = await getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions',
    z.array(z.unknown()),
    {
      params: { path: { strategy_type: strategyType } },
      signal,
    },
  );
  return data.map(normalizeVersionSummary);
}

/** Every saved research run for one memory version, newest first. */
export async function getVersionRuns(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<VersionRunSummary[]> {
  const payload = await openapiGet(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/runs',
    {
      params: { path: { strategy_type: strategyType, memory_version: memoryVersion } },
      signal,
    },
  );
  const rows = Array.isArray((payload as Record<string, unknown>)?.data)
    ? ((payload as Record<string, unknown>).data as unknown[])
    : [];
  return rows.map(normalizeVersionRun);
}

export async function getVersionFinal(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<VersionFinal> {
  // No Zod schema covers `BacktestDetail`; the body stays an unvalidated cast.
  return (await openapiGet(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/final',
    {
      params: { path: { strategy_type: strategyType, memory_version: memoryVersion } },
      signal,
    },
  )) as VersionFinal;
}

export async function getVersionSurface(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<ResearchStrategySurface> {
  return getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/surface',
    researchSurfaceSchema,
    {
      params: { path: { strategy_type: strategyType, memory_version: memoryVersion } },
      signal,
    },
  );
}

export async function getVersionSingleAsset(
  strategyType: string,
  memoryVersion: string,
  asset: string | null,
  signal?: AbortSignal,
  configId: string | null = null,
): Promise<SingleAssetView> {
  return getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/single-asset',
    singleAssetViewSchema,
    {
      params: {
        path: { strategy_type: strategyType, memory_version: memoryVersion },
        query: { asset: asset ?? undefined, config_id: configId ?? undefined },
      },
      signal,
    },
  );
}

export async function getVersionSurfaceGrid(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<ResearchGrid> {
  return getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/surface/grid',
    researchGridSchema,
    {
      params: { path: { strategy_type: strategyType, memory_version: memoryVersion } },
      signal,
    },
  );
}

export async function getVersionSurfaceGridConfiguration(
  strategyType: string,
  memoryVersion: string,
  configId: string,
  signal?: AbortSignal,
): Promise<ResearchGridConfiguration> {
  return getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/surface/grid/configurations/{config_id}',
    researchGridConfigurationSchema,
    {
      params: {
        path: {
          strategy_type: strategyType,
          memory_version: memoryVersion,
          config_id: configId,
        },
      },
      signal,
    },
  );
}

export async function getVersionSurfaceRank(
  strategyType: string,
  memoryVersion: string,
  signal?: AbortSignal,
): Promise<VersionRank> {
  return getParsed(
    '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/surface/rank',
    versionRankSchema,
    {
      params: { path: { strategy_type: strategyType, memory_version: memoryVersion } },
      signal,
    },
  );
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const strategyKeys = {
  all: ['strategies'] as const,
  types: () => [...strategyKeys.all, 'types'] as const,
  versions: (strategyType: string) => [...strategyKeys.all, 'versions', strategyType] as const,
  runs: (strategyType: string, memoryVersion: string) =>
    [...strategyKeys.all, 'runs', strategyType, memoryVersion] as const,
  final: (strategyType: string, memoryVersion: string) =>
    [...strategyKeys.all, 'final', strategyType, memoryVersion] as const,
  surface: (strategyType: string, memoryVersion: string) =>
    [...strategyKeys.all, 'surface', strategyType, memoryVersion] as const,
  singleAsset: (
    strategyType: string,
    memoryVersion: string,
    selectedRunId: string | null,
    asset: string | null,
    configId: string | null = null,
  ) =>
    [
      ...strategyKeys.all,
      'single-asset',
      strategyType,
      memoryVersion,
      selectedRunId,
      configId,
      asset,
    ] as const,
  grid: (strategyType: string, memoryVersion: string) =>
    [...strategyKeys.all, 'surface', strategyType, memoryVersion, 'grid'] as const,
  gridConfiguration: (strategyType: string, memoryVersion: string, configId: string) =>
    [...strategyKeys.grid(strategyType, memoryVersion), 'configuration', configId] as const,
  rank: (strategyType: string, memoryVersion: string) =>
    [...strategyKeys.surface(strategyType, memoryVersion), 'rank'] as const,
};

export function useStrategyTypes() {
  return useQuery({
    queryKey: strategyKeys.types(),
    queryFn: ({ signal }) => listStrategyTypes(signal),
    staleTime: STALE.list,
  });
}

export function useStrategyVersions(strategyType: string) {
  return useQuery({
    queryKey: strategyKeys.versions(strategyType),
    queryFn: ({ signal }) => listStrategyVersions(strategyType, signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType),
  });
}
