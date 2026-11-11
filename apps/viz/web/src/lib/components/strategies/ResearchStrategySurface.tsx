/**
 * Research strategy-version surface: portfolio chart, comparison, promotion gates.
 *
 * USAGE:
 *   <ResearchStrategySurface strategyType="…" memoryVersion="v003" surface={…} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { MultiSeriesTimeChart } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor, chartPaletteColor } from '@quant-factory/qf-ui/charts/theme';
import {
  DataTable,
  type MetricComparisonColumn,
  type MetricComparisonRow,
  MetricComparisonTable,
} from '@quant-factory/qf-ui/tables';
import { Suspense, useState } from 'react';
import { strategyExtraMetrics } from '@/extensions';
import { useBenchmark, useBenchmarks } from '@/lib/api/benchmarks';
import type { DatasetChartBundleSeries } from '@/lib/api/catalog';
import type { ResearchStrategySurface as Surface } from '@/lib/api/strategies';
import {
  Banner,
  Button,
  formatCount,
  formatMoney,
  formatNumber,
  formatPercent,
  LoadingSkeleton,
  lazyNamed,
  Section,
  Stack,
  Text,
} from '@/ui';
import { STANDARD_METRICS, sortColumnsBySortino } from './performance-metrics';
import {
  buildBuyHoldSeries,
  buyHoldMetric,
  defaultOverlayTicker,
  isRegisteredBenchmark,
  performanceValuePresentation,
  shouldAddBuyHoldOverlay,
} from './research-strategy-chart-model';

const OptimizerGridSurface = lazyNamed(
  () => import('./OptimizerGridSurface'),
  'OptimizerGridSurface',
);
const CategoricalGridSurface = lazyNamed(
  () => import('./CategoricalGridSurface'),
  'CategoricalGridSurface',
);

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ResearchStrategySurfaceProps {
  strategyType: string;
  memoryVersion: string;
  surface: Surface;
  operatorBaselineVersion?: string | null;
  operatorBaselineSurface?: Surface;
  currentDataReplay?: {
    label: string;
    sourceSeries: 'strategy' | 'benchmark';
    surface?: Surface;
  };
}

type SurfaceRow = Surface['data'][number];
type PerformanceRow = Extract<SurfaceRow, { date: string }>;
type PnlRow = Extract<SurfaceRow, { timestamp: string }>;

function isPerformanceRow(row: SurfaceRow): row is PerformanceRow {
  return 'date' in row;
}

function isPnlRow(row: SurfaceRow): row is PnlRow {
  return 'timestamp' in row;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const BENCHMARK_COLOR = chartColor('benchmark');

function formatValue(value: number | string | null, format: string): string {
  if (value === null || (typeof value === 'number' && !Number.isFinite(value))) return '—';
  if (format === 'text') return String(value);
  if (typeof value === 'string') return value;
  if (format === 'percent') return formatPercent(value, 2);
  if (format === 'money') return formatMoney(value, 2);
  if (Number.isInteger(value)) return formatCount(value);
  return formatNumber(value, 3);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ResearchStrategySurface({
  strategyType,
  memoryVersion,
  surface,
  operatorBaselineVersion,
  operatorBaselineSurface,
  currentDataReplay,
}: ResearchStrategySurfaceProps) {
  const matrix = surface.variant_matrices[0];
  const variants = matrix?.variants ?? [];
  const benchmarkOptions = useBenchmarks().data ?? [];
  const tickers = benchmarkOptions.map((option) => option.ticker);
  const performanceRows = surface.data.filter(isPerformanceRow);
  const pnlRows = surface.data.filter(isPnlRow);
  const performance =
    surface.metrics && surface.benchmark && performanceRows.length > 0
      ? { benchmark: surface.benchmark, metrics: surface.metrics }
      : null;
  const operatorBaselineRows = operatorBaselineSurface?.data.filter(isPerformanceRow) ?? [];
  const currentDataReplayRows = currentDataReplay?.surface?.data.filter(isPerformanceRow) ?? [];
  const baseline =
    operatorBaselineVersion &&
    operatorBaselineSurface?.memory_version === operatorBaselineVersion &&
    operatorBaselineSurface.strategy_type === strategyType &&
    operatorBaselineSurface.metrics &&
    operatorBaselineRows.length > 0 &&
    operatorBaselineSurface.performance_unit === surface.performance_unit
      ? {
          label: `${operatorBaselineVersion} current baseline`,
          detail: 'Selected baseline · original recorded period',
          metrics: operatorBaselineSurface.metrics.strategy,
          sameRun: false,
          points: operatorBaselineRows.map((row) => ({
            x: `${row.date.slice(0, 10)}T00:00:00`,
            y: row.strategy_portfolio_value,
          })),
        }
      : null;
  const baselineSeries: DatasetChartBundleSeries | null = baseline
    ? {
        metric: 'operator_baseline',
        axis: 'left',
        label: baseline.label,
        points_total: operatorBaselineSurface?.points_total ?? baseline.points.length,
        points_returned: baseline.points.length,
        points: baseline.points,
      }
    : null;
  const comparison = (() => {
    if (
      currentDataReplay?.surface?.metrics &&
      currentDataReplayRows.length > 0 &&
      currentDataReplay.surface.performance_unit === surface.performance_unit
    ) {
      const source = currentDataReplay.sourceSeries;
      return {
        label: currentDataReplay.label,
        detail: 'Current-data replay',
        metrics: currentDataReplay.surface.metrics[source],
        sameRun: false,
        points: currentDataReplayRows.map((row) => ({
          x: `${row.date.slice(0, 10)}T00:00:00`,
          y: source === 'strategy' ? row.strategy_portfolio_value : row.benchmark_portfolio_value,
        })),
      };
    }
    if (surface.comparison)
      return {
        label: surface.comparison.label,
        detail: 'Registered comparison · same run',
        metrics: surface.comparison.metrics,
        sameRun: true,
        points: surface.comparison.data.map((row) => ({
          x: `${row.date.slice(0, 10)}T00:00:00`,
          y: row.portfolio_value,
        })),
      };
    if (
      performance &&
      performance.benchmark.id !== 'cash' &&
      !isRegisteredBenchmark(performance.benchmark, tickers)
    )
      return {
        label: performance.benchmark.label,
        detail: 'Registered comparison · same run',
        metrics: performance.metrics.benchmark,
        sameRun: true,
        points: performanceRows.map((row) => ({
          x: `${row.date.slice(0, 10)}T00:00:00`,
          y: row.benchmark_portfolio_value,
        })),
      };
    if (!surface.comparison_issue) return baseline;
    return null;
  })();
  const benchmarkIsMarket = performance
    ? isRegisteredBenchmark(performance.benchmark, tickers)
    : false;
  const needsOverlay = performance
    ? shouldAddBuyHoldOverlay(strategyType, performance.benchmark, tickers)
    : false;
  const chartDates = [
    ...new Set([
      ...performanceRows.map((row) => row.date),
      ...(comparison?.points.map((point) => point.x.slice(0, 10)) ?? []),
      ...(baseline?.points.map((point) => point.x.slice(0, 10)) ?? []),
    ]),
  ].sort();
  const startDate = chartDates[0]?.slice(0, 10);
  const endDate = chartDates.at(-1)?.slice(0, 10);
  // null follows the strategy's declared benchmark, else the first registered one.
  const [overlayChoice, setOverlayChoice] = useState<string | null>(null);
  const overlayTicker =
    overlayChoice && tickers.includes(overlayChoice)
      ? overlayChoice
      : defaultOverlayTicker(strategyType, tickers);
  const overlay = benchmarkOptions.find((option) => option.ticker === overlayTicker) ?? null;
  const overlayQuery = useBenchmark(
    needsOverlay && overlay && startDate && endDate ? overlay.ticker : '',
    startDate,
    endDate,
  );
  const overlaySeries =
    needsOverlay && overlay
      ? buildBuyHoldSeries(chartDates, overlayQuery.data?.data ?? [], overlay, {
          mainScale: true,
        })
      : null;
  const nextOverlayTicker = overlayTicker
    ? tickers[(tickers.indexOf(overlayTicker) + 1) % tickers.length]
    : undefined;
  const overlayToggle =
    needsOverlay && overlayTicker && nextOverlayTicker && tickers.length > 1 ? (
      <Button
        variant="control"
        aria-label={`Buy-and-hold overlay: ${overlayTicker}. Switch to ${nextOverlayTicker}`}
        title={`Switch to ${nextOverlayTicker}`}
        onClick={() => setOverlayChoice(nextOverlayTicker)}
      >
        vs {overlayTicker}
      </Button>
    ) : undefined;
  const valuePresentation = performanceValuePresentation(surface.performance_unit ?? 'usd');
  const categoricalGrid = surface.grid?.dimensions.some((dimension) => dimension.format === 'text');
  const pageSummary =
    surface.grid && !categoricalGrid
      ? `${surface.grid.summary.row_count} static OOS configurations compared with the static control and ${performance?.benchmark.label ?? 'the declared benchmark'}.`
      : surface.summary;
  const comparisonVersion = comparison?.label.match(/\bv\d{3}\b/i)?.[0];
  // A bare version that repeats this page's own version says nothing; keep the full label instead.
  const comparisonTitle =
    comparisonVersion && comparisonVersion !== memoryVersion
      ? comparisonVersion
      : comparison?.label;
  const comparisonColumns: MetricComparisonColumn[] = [
    {
      id: 'strategy',
      label: variants[0]?.label ?? memoryVersion,
      detail: currentDataReplay ? 'Sealed candidate' : 'Current candidate',
      color: chartColor(1),
    },
    ...(comparison
      ? [
          {
            id: 'comparison',
            label: comparisonTitle ?? comparison.label,
            description: comparison.label,
            detail: comparison.detail,
            color: comparison === baseline ? chartColor('baseline') : chartColor(2),
          },
        ]
      : []),
    ...(benchmarkIsMarket && performance
      ? [
          {
            id: 'benchmark',
            label: performance.benchmark.label,
            detail: 'Market benchmark',
            color: BENCHMARK_COLOR,
          },
        ]
      : []),
  ];
  const comparisonRows: MetricComparisonRow[] = performance
    ? [
        ...STANDARD_METRICS.map((metric) => ({
          ...metric,
          label: metric.key === 'ending_value' ? valuePresentation.endingValueLabel : metric.label,
          format:
            metric.key === 'ending_value' ? valuePresentation.endingValueFormat : metric.format,
          values: {
            strategy: performance.metrics.strategy[metric.key],
            comparison: comparison?.metrics[metric.key],
            benchmark: performance.metrics.benchmark[metric.key],
          },
        })),
        ...strategyExtraMetrics(strategyType).map((metric) => ({
          key: metric.key,
          group: 'Research diagnostics',
          label: metric.label,
          format: metric.format ?? 'number',
          higherIsBetter: metric.higherIsBetter,
          values: {
            strategy: metric.resolve(performance.metrics.strategy),
            comparison: comparison ? metric.resolve(comparison.metrics) : null,
          },
        })),
        ...surface.diagnostics.map((metric) => ({
          ...metric,
          group: 'Research diagnostics',
          values: { strategy: metric.value },
        })),
      ]
    : [];
  const recordRows = surface.diagnostics.map((metric) => ({
    Item: metric.label,
    Result: formatValue(metric.value, metric.format),
  }));

  const gateRows = surface.gates.map((gate) => ({
    Gate: gate.name,
    Requirement: gate.requirement,
    Result: formatValue(gate.result, gate.format),
    Status: gate.passed ? 'Pass' : 'Fail',
  }));

  const chartSeries: DatasetChartBundleSeries[] = performance
    ? [
        ...(variants.length > 0
          ? variants.map((variant) => ({
              metric: variant.id,
              axis: 'left' as const,
              label: variant.label,
              points_total: surface.points_total,
              points_returned: variant.data.length,
              points: variant.data.map((row) => ({
                x: `${row.date}T00:00:00`,
                y: row.portfolio_value,
              })),
            }))
          : [
              {
                metric: 'strategy',
                axis: 'left' as const,
                label: currentDataReplay ? `${memoryVersion} sealed` : memoryVersion,
                points_total: surface.points_total,
                points_returned: surface.points_returned,
                points: performanceRows.map((row) => ({
                  x: `${row.date.slice(0, 10)}T00:00:00`,
                  y: row.strategy_portfolio_value,
                })),
              },
            ]),
        ...(comparison && comparison !== baseline
          ? [
              {
                metric: 'comparison',
                axis: 'left' as const,
                label: comparison.label,
                points_total: comparison.points.length,
                points_returned: comparison.points.length,
                points: comparison.points,
              },
            ]
          : []),
        ...(baselineSeries ? [baselineSeries] : []),
        ...(benchmarkIsMarket
          ? [
              {
                metric: 'benchmark',
                axis: 'left' as const,
                label: performance.benchmark.label,
                isBenchmark: true,
                points_total: surface.points_total,
                points_returned: surface.points_returned,
                points: performanceRows.map((row) => ({
                  x: `${row.date.slice(0, 10)}T00:00:00`,
                  y: row.benchmark_portfolio_value,
                })),
              },
            ]
          : []),
        ...(overlaySeries ? [overlaySeries] : []),
      ]
    : [];
  const matrixColumns: MetricComparisonColumn[] = variants.map((variant, index) => ({
    id: variant.id,
    label: variant.label,
    color: chartPaletteColor(index),
  }));
  const matrixRows: MetricComparisonRow[] = [
    ...STANDARD_METRICS.map((metric) => ({
      ...metric,
      label: metric.key === 'ending_value' ? valuePresentation.endingValueLabel : metric.label,
      format: metric.key === 'ending_value' ? valuePresentation.endingValueFormat : metric.format,
      values: Object.fromEntries(
        variants.map((variant) => [variant.id, variant.metrics[metric.key]]),
      ),
    })),
    ...(variants.some((variant) => variant.gross_return !== undefined)
      ? [
          {
            key: 'gross_return',
            group: 'Before fees',
            label: 'Return before fees',
            format: 'percent' as const,
            higherIsBetter: true,
            values: Object.fromEntries(
              variants.map((variant) => [variant.id, variant.gross_return]),
            ),
          },
        ]
      : []),
    ...(variants.some((variant) => variant.gross_sharpe !== undefined)
      ? [
          {
            key: 'gross_sharpe',
            group: 'Before fees',
            label: 'Sharpe before fees',
            format: 'number' as const,
            higherIsBetter: true,
            values: Object.fromEntries(
              variants.map((variant) => [variant.id, variant.gross_sharpe]),
            ),
          },
        ]
      : []),
  ];
  const metricColors = {
    ...Object.fromEntries(variants.map((variant, index) => [variant.id, chartPaletteColor(index)])),
    strategy: chartColor(1),
    comparison: chartColor(2),
    operator_baseline: chartColor('baseline'),
    benchmark: BENCHMARK_COLOR,
    ...(overlay ? { [buyHoldMetric(overlay.ticker)]: BENCHMARK_COLOR } : {}),
  };
  const pnlSeries: DatasetChartBundleSeries[] = surface.pnl
    ? [
        {
          metric: 'cumulative_pnl_usd',
          axis: 'left',
          label: surface.pnl.label,
          points_total: surface.points_total,
          points_returned: surface.points_returned,
          points: pnlRows.map((row) => ({
            x: row.timestamp,
            y: row.cumulative_pnl_usd,
          })),
        },
        ...(surface.benchmark && surface.pnl.columns.length === 3
          ? [
              {
                metric: 'benchmark_cumulative_pnl_usd',
                axis: 'left' as const,
                label: surface.benchmark.label,
                isBenchmark: isRegisteredBenchmark(surface.benchmark, tickers),
                points_total: surface.points_total,
                points_returned: surface.points_returned,
                points: pnlRows.flatMap((row) =>
                  row.benchmark_cumulative_pnl_usd === undefined
                    ? []
                    : [{ x: row.timestamp, y: row.benchmark_cumulative_pnl_usd }],
                ),
              },
            ]
          : []),
      ]
    : [];

  return (
    <>
      {surface.pnl ? (
        <Section>
          <Stack gap="heading">
            <Text as="h3" size="base" weight="bold">
              Backtest PnL over time
            </Text>
            <MultiSeriesTimeChart
              title={`Cumulative PnL — $${surface.pnl.allocation_usd.toFixed(0)} per trade${
                surface.benchmark ? ` · ${memoryVersion} vs ${surface.benchmark.label}` : ''
              }`}
              series={pnlSeries}
              interpolation="step-end"
              metricColors={{
                cumulative_pnl_usd: chartColor(1),
                benchmark_cumulative_pnl_usd: chartColor(8),
              }}
              valueFormat="money"
            />
            {surface.pnl.interpretation === 'protocol_stop' ? (
              <Text as="p" tone="muted" size="xs">
                Flat at $0 because the protocol stopped before any admissible trades were scored.
              </Text>
            ) : null}
          </Stack>
        </Section>
      ) : null}

      {needsOverlay && overlayQuery.error && !overlayQuery.data ? (
        <Banner tone="warning">
          {overlayTicker} overlay unavailable: {overlayQuery.error.message}
        </Banner>
      ) : null}
      {surface.grid ? (
        <Suspense fallback={<LoadingSkeleton variant="chart" />}>
          {categoricalGrid ? (
            <CategoricalGridSurface
              strategyType={strategyType}
              memoryVersion={memoryVersion}
              benchmarkSeries={overlaySeries ? { ...overlaySeries, isBenchmark: true } : null}
              baselineSeries={baselineSeries}
            />
          ) : (
            <OptimizerGridSurface
              key={`${memoryVersion}-${surface.run_id}`}
              strategyType={strategyType}
              memoryVersion={memoryVersion}
              metadata={surface.grid}
              baselineSeries={baselineSeries}
            />
          )}
        </Suspense>
      ) : performance ? (
        <>
          <Section>
            <MultiSeriesTimeChart
              title={`${valuePresentation.chartPrefix} · ${memoryVersion}${comparison ? ` vs ${comparisonTitle}` : ''}`}
              series={chartSeries}
              metricColors={metricColors}
              headerRight={overlayToggle}
              yScaleType={overlaySeries ? 'log' : 'linear'}
              valueFormat={surface.performance_unit === 'index' ? 'number' : 'money'}
            />
          </Section>
          <Section title="Performance comparison">
            <MetricComparisonTable
              columns={comparisonColumns}
              rows={comparisonRows}
              difference={
                comparison?.sameRun ? { current: 'strategy', reference: 'comparison' } : undefined
              }
            />
          </Section>
          {variants.length > 0 ? (
            <Section title={`${matrix?.title ?? 'Variant matrix'} · Sortino ↓`}>
              <MetricComparisonTable
                columns={sortColumnsBySortino(matrixColumns, matrixRows)}
                rows={matrixRows}
              />
            </Section>
          ) : null}
        </>
      ) : (
        <Section title="What this version did">
          <Stack gap="block">
            <Text as="p" tone="muted" size="sm">
              {surface.summary}
            </Text>
            {recordRows.length > 0 ? (
              <DataTable
                data={recordRows}
                columns={['Item', 'Result']}
                maxRows={recordRows.length}
              />
            ) : null}
          </Stack>
        </Section>
      )}

      {surface.grid && recordRows.length > 0 ? (
        <Section title="Research diagnostics">
          <DataTable data={recordRows} columns={['Item', 'Result']} maxRows={recordRows.length} />
        </Section>
      ) : null}
      {gateRows.length > 0 ? (
        <Section title="Measurement checks">
          <DataTable
            data={gateRows}
            columns={['Gate', 'Requirement', 'Result', 'Status']}
            maxRows={gateRows.length}
          />
        </Section>
      ) : null}
      <Section title="Research notes">
        <Text as="p" tone="muted" size="sm">
          {pageSummary}
        </Text>
        {surface.comparison_issue ? (
          <Text as="p" tone="muted" size="sm">
            {surface.comparison_issue}
          </Text>
        ) : null}
        {currentDataReplay && !comparison ? (
          <Text as="p" tone="muted" size="sm">
            {currentDataReplay.label} unavailable.
          </Text>
        ) : null}
        {operatorBaselineVersion && !baseline ? (
          <Text as="p" tone="muted" size="sm">
            {operatorBaselineVersion} baseline overlay unavailable.
          </Text>
        ) : null}
        {baseline ? (
          <Text as="p" tone="muted" size="sm">
            {baseline.label}: {baseline.points[0]?.x.slice(0, 10)} –{' '}
            {baseline.points.at(-1)?.x.slice(0, 10)}. Original recorded period; the line ends where
            baseline data ends.
          </Text>
        ) : null}
        {surface.disclosures.map((disclosure) => (
          <Text key={disclosure} as="p" tone="muted" size="sm">
            {disclosure}
          </Text>
        ))}
      </Section>
    </>
  );
}
