/**
 * Interactive 2D optimizer response surface with complete-path comparison.
 *
 * USAGE:
 *   <OptimizerGridSurface strategyType="family" memoryVersion="v011" metadata={surface.grid} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QF_CHART_ASPECT_RATIO } from '@quant-factory/qf-ui/charts/core';
import {
  MultiSeriesTimeChart,
  type MultiSeriesTimeChartProps,
  OptimizerGrid,
  type OptimizerGridRow,
  type OptimizerGridSelection,
} from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { MetricComparisonTable } from '@quant-factory/qf-ui/tables';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { useBenchmark, useBenchmarks } from '@/lib/api/benchmarks';
import type { DatasetChartBundleSeries } from '@/lib/api/catalog';
import { STALE } from '@/lib/api/stale-times';
import {
  getVersionSurfaceGrid,
  getVersionSurfaceGridConfiguration,
  type ResearchStrategySurface,
  strategyKeys,
} from '@/lib/api/strategies';
import {
  EmptyState,
  ErrorPanel,
  isLoadingData,
  LoadingSkeleton,
  ScrollArea,
  Section,
  Stack,
  Text,
} from '@/ui';
import { compareSortinoValues, STANDARD_METRICS } from './performance-metrics';

import {
  buildBuyHoldSeries,
  buyHoldLabel,
  buyHoldMetric,
  defaultOverlayTicker,
  duplicatesSeries,
  isRegisteredBenchmark,
  shouldAddBuyHoldOverlay,
} from './research-strategy-chart-model';

// --------------------------------------------------------------------------- #
// Types and constants
// --------------------------------------------------------------------------- #

type GridMetadata = NonNullable<ResearchStrategySurface['grid']>;

export interface OptimizerGridSurfaceProps {
  strategyType: string;
  memoryVersion: string;
  metadata: GridMetadata;
  baselineSeries?: DatasetChartBundleSeries | null;
}

// --------------------------------------------------------------------------- #
// Display helpers
// --------------------------------------------------------------------------- #

function initialKey(candidate: string | null, valid: string[], fallback: string): string {
  return candidate && valid.includes(candidate) ? candidate : fallback;
}

function finiteGridValue(row: Record<string, unknown>, key: string): number {
  const value = row[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Optimizer grid value “${key}” is not finite`);
  }
  return value;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function OptimizerGridSurface({
  strategyType,
  memoryVersion,
  metadata,
  baselineSeries,
}: OptimizerGridSurfaceProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const dimensionKeys = metadata.dimensions.map((dimension) => dimension.key);
  const metricKeys = [
    ...new Set(['sortino', 'martin', ...metadata.metrics.map((metric) => metric.key)]),
  ];
  const defaultX = dimensionKeys.includes('turnover_penalty_rate')
    ? 'turnover_penalty_rate'
    : (dimensionKeys[0] ?? '');
  const defaultY = dimensionKeys.includes('volatility_target')
    ? 'volatility_target'
    : (dimensionKeys.find((key) => key !== defaultX) ?? dimensionKeys[1] ?? '');
  const requestedX = initialKey(searchParams.get('x'), dimensionKeys, defaultX);
  const requestedY = initialKey(searchParams.get('y'), dimensionKeys, defaultY);
  const [xKey, setXKey] = useState(requestedX);
  const [yKey, setYKey] = useState(requestedY === requestedX ? defaultY : requestedY);
  const [metricKey, setMetricKey] = useState(
    initialKey(searchParams.get('metric'), metricKeys, 'sortino'),
  );
  const [selectedId, setSelectedId] = useState(
    searchParams.get('config') ?? metadata.selected_config_id,
  );

  const gridQuery = useQuery({
    queryKey: strategyKeys.grid(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionSurfaceGrid(strategyType, memoryVersion, signal),
    // Pinned to a memory version; optimizer surface artifacts publish once and never mutate.
    staleTime: STALE.analysis,
    retry: false,
  });
  const grid = gridQuery.data;
  const selected =
    grid?.data.find((row) => row.config_id === selectedId) ??
    grid?.data.find((row) => row.config_id === metadata.selected_config_id) ??
    null;
  const effectiveSelectedId = selected?.config_id ?? metadata.selected_config_id;
  const detailQuery = useQuery({
    queryKey: strategyKeys.gridConfiguration(strategyType, memoryVersion, effectiveSelectedId),
    queryFn: ({ signal }) =>
      getVersionSurfaceGridConfiguration(strategyType, memoryVersion, effectiveSelectedId, signal),
    // Pinned to a memory version + config id; optimizer surface artifacts publish once and never mutate.
    staleTime: STALE.analysis,
    enabled: selected != null,
    retry: false,
  });
  const detail = detailQuery.data;
  const benchmarkOptions = useBenchmarks().data ?? [];
  const tickers = benchmarkOptions.map((option) => option.ticker);
  const overlayTicker = defaultOverlayTicker(strategyType, tickers);
  const overlay = benchmarkOptions.find((option) => option.ticker === overlayTicker) ?? null;
  const needsOverlay =
    detail != null &&
    overlay != null &&
    shouldAddBuyHoldOverlay(strategyType, detail.benchmark, tickers);
  const startDate = detail?.data[0]?.date.slice(0, 10);
  const endDate = detail?.data.at(-1)?.date.slice(0, 10);
  const overlayQuery = useBenchmark(
    needsOverlay && overlay && startDate && endDate ? overlay.ticker : '',
    startDate,
    endDate,
  );
  const overlaySeries =
    needsOverlay && overlay
      ? buildBuyHoldSeries(
          detail.data.map((row) => row.date),
          overlayQuery.data?.data ?? [],
          overlay,
        )
      : null;
  const overlayLabel = overlay ? buyHoldLabel(overlay.label) : '';

  const updateLocation = (next: { metric?: string; x?: string; y?: string; config?: string }) => {
    const params = new URLSearchParams(searchParams);
    params.set('metric', next.metric ?? metricKey);
    params.set('x', next.x ?? xKey);
    params.set('y', next.y ?? yKey);
    params.set('config', next.config ?? effectiveSelectedId);
    setSearchParams(params, { replace: true });
  };

  if (gridQuery.error && !grid) {
    return (
      <Section title="Optimizer response surface">
        <ErrorPanel
          message={gridQuery.error.message}
          onRetry={() => {
            void gridQuery.refetch();
          }}
        />
      </Section>
    );
  }
  if (isLoadingData(gridQuery) || !grid) {
    return (
      <Section title="Optimizer response surface">
        <LoadingSkeleton variant="chart" />
      </Section>
    );
  }
  if (!selected) {
    return (
      <Section title="Optimizer response surface">
        <EmptyState title="Grid selection unavailable" hint="No selected default configuration" />
      </Section>
    );
  }

  const updateGridSelection = (next: OptimizerGridSelection) => {
    setMetricKey(next.metricKey);
    setXKey(next.xKey);
    setYKey(next.yKey);
    setSelectedId(next.rowId);
    updateLocation({
      metric: next.metricKey,
      x: next.xKey,
      y: next.yKey,
      config: next.rowId,
    });
  };
  // Null portfolio values are dates outside that role's observed coverage; the chart breaks there.
  const chartSeries: MultiSeriesTimeChartProps['series'][number][] = detail
    ? [
        {
          metric: 'selected',
          axis: 'left',
          label: `Selected #${detail.config.rank}`,
          points: detail.data.map((row) => ({
            x: `${row.date.slice(0, 10)}T00:00:00`,
            y: row.selected_portfolio_value,
          })),
        },
        {
          metric: 'control',
          axis: 'left',
          label: 'Static control',
          points: detail.data.map((row) => ({
            x: `${row.date.slice(0, 10)}T00:00:00`,
            y: row.control_portfolio_value,
          })),
        },
        {
          metric: 'benchmark',
          axis: 'left',
          label: detail.benchmark.label,
          isBenchmark: isRegisteredBenchmark(detail.benchmark, tickers),
          points: detail.data.map((row) => ({
            x: `${row.date.slice(0, 10)}T00:00:00`,
            y: row.benchmark_portfolio_value,
          })),
        },
      ]
    : [];
  if (baselineSeries && !duplicatesSeries(baselineSeries, chartSeries))
    chartSeries.push(baselineSeries);
  if (overlaySeries) chartSeries.push(overlaySeries);
  const comparisonRows = detail
    ? STANDARD_METRICS.map((metric) => ({
        ...metric,
        values: {
          selected: detail.metrics.selected[metric.key],
          control: detail.metrics.control[metric.key],
          benchmark: detail.metrics.benchmark?.[metric.key] ?? null,
        },
      }))
    : [];
  const optimizerRows: OptimizerGridRow[] = [...grid.data]
    .sort((a, b) => compareSortinoValues(a.sortino, b.sortino))
    .map((row, index) => ({
      id: row.config_id,
      rank: index + 1,
      isControl: row.is_control,
      values: Object.fromEntries([
        ...grid.dimensions.map(({ key }) => [key, finiteGridValue(row, key)]),
        ...grid.metrics.map(({ key }) => [
          key,
          typeof row[key] === 'number' && Number.isFinite(row[key]) ? row[key] : null,
        ]),
      ]),
    }));

  return (
    <>
      <Section>
        <ScrollArea
          axis="both"
          className="min-w-0"
          style={{ aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` }}
        >
          <OptimizerGrid
            dimensions={grid.dimensions.filter((dimension) => dimension.format !== 'text')}
            metrics={grid.metrics.map((metric) => ({
              key: metric.key,
              label: metric.label,
              format: metric.format,
              higherIsBetter: metric.higher_is_better,
            }))}
            rows={optimizerRows}
            selection={{
              metricKey,
              xKey,
              yKey,
              rowId: selected.config_id,
            }}
            onChange={updateGridSelection}
            ariaLabel="Optimizer response surface"
            accentColor={chartColor(1)}
            surfaceColor="var(--color-chart-surface)"
            controlLabel="Static control"
            intro="Ranks use Sortino, highest first. Other metrics provide context. Undefined metric cells are blank."
          />
        </ScrollArea>
      </Section>

      <Section>
        <Stack gap="heading">
          <Text as="h3" size="base" weight="bold">
            Selected static path vs control and benchmark
          </Text>
          {isLoadingData(detailQuery) ? (
            <LoadingSkeleton variant="chart" label="Loading selected optimizer path" />
          ) : null}
          {detailQuery.error && !detail ? (
            <ErrorPanel
              message={detailQuery.error.message}
              onRetry={() => {
                void detailQuery.refetch();
              }}
            />
          ) : null}
          {needsOverlay && isLoadingData(overlayQuery) ? (
            <LoadingSkeleton variant="chart" label={`Loading ${overlayLabel} comparison`} />
          ) : needsOverlay && overlayQuery.error && !overlayQuery.data ? (
            <ErrorPanel
              message={`${overlayLabel} failed to load: ${overlayQuery.error.message}`}
              onRetry={() => {
                void overlayQuery.refetch();
              }}
            />
          ) : needsOverlay && !overlaySeries ? (
            <EmptyState
              title={`${overlayLabel} unavailable`}
              hint={`No ${overlay?.label} observations overlap the selected strategy dates, so the comparison chart is withheld.`}
            />
          ) : detail ? (
            <MultiSeriesTimeChart
              title={`$100 portfolios — selected #${detail.config.rank} vs control vs ${
                overlaySeries
                  ? `${detail.benchmark.label} vs ${overlayLabel}`
                  : detail.benchmark.label
              }`}
              series={chartSeries}
              metricColors={{
                selected: chartColor(1),
                control: chartColor(2),
                benchmark: needsOverlay ? chartColor(2) : chartColor(3),
                ...(overlay ? { [buyHoldMetric(overlay.ticker)]: chartColor(3) } : {}),
                ...(baselineSeries ? { [baselineSeries.metric]: chartColor('baseline') } : {}),
              }}
            />
          ) : null}
        </Stack>
      </Section>

      {detail ? (
        <Section title="Selected configuration comparison">
          <MetricComparisonTable
            columns={[
              {
                id: 'selected',
                label: `Selected #${detail.config.rank}`,
                detail: 'Current candidate',
                color: chartColor(1),
              },
              {
                id: 'control',
                label: 'Control',
                detail: 'Registered comparison',
                color: chartColor(2),
              },
              { id: 'benchmark', label: detail.benchmark.label, detail: 'Benchmark' },
            ]}
            rows={comparisonRows}
            difference={{ current: 'selected', reference: 'control' }}
          />
        </Section>
      ) : null}
    </>
  );
}
