/** Categorical research variants: all paths and their performance matrix.
 * The matrix switches between recorded Values and on-demand Rank against the
 * family's other published versions (fetched only when Rank is selected).
 * USAGE: <CategoricalGridSurface strategyType="family" memoryVersion="v009" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  PortfolioDrawdownChart,
  type PortfolioDrawdownChartProps,
} from '@quant-factory/qf-ui/charts/renderers';
import { chartColor, chartPaletteColor } from '@quant-factory/qf-ui/charts/theme';
import {
  type MetricComparisonColumn,
  type MetricComparisonRow,
  MetricComparisonTable,
  type MetricComparisonView,
} from '@quant-factory/qf-ui/tables';
import { type UseQueryResult, useQueries, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { strategyGridCurveCostBps } from '@/extensions';
import type { DatasetChartBundleSeries } from '@/lib/api/catalog';
import { STALE } from '@/lib/api/stale-times';
import {
  getVersionSurfaceGrid,
  getVersionSurfaceGridConfiguration,
  getVersionSurfaceRank,
  strategyKeys,
  type VersionRank,
} from '@/lib/api/strategies';
import {
  EmptyState,
  ErrorPanel,
  InfoTip,
  LoadingSkeleton,
  Section,
  SegmentedControl,
  Stack,
  Text,
} from '@/ui';
import {
  attachMetricRanks,
  buildPerformanceMatrixRows,
  sortColumnsBySortino,
} from './performance-metrics';
import { duplicatesSeries } from './research-strategy-chart-model';

const VIEW_OPTIONS: Array<{ value: MetricComparisonView; label: string }> = [
  { value: 'values', label: 'Values' },
  { value: 'rank', label: 'Rank' },
];
const UNRANKED_NOTE =
  'Not ranked: exposure, activity and dollar diagnostics have no comparable better or worse direction.';

// --------------------------------------------------------------------------- #
// Rank view: family comparison context and states
// --------------------------------------------------------------------------- #

function RankContext({
  rank,
}: {
  rank: VersionRank & { window: NonNullable<VersionRank['window']> };
}) {
  const reasons = new Map<string, string[]>();
  for (const item of rank.excluded) {
    reasons.set(item.detail, [...(reasons.get(item.detail) ?? []), item.memory_version]);
  }
  const { window } = rank;
  return (
    <Stack gap="xs">
      <Text variant="label" as="p">
        {rank.label} · {window.start_mark} start to {window.end} ·{' '}
        {window.observations.toLocaleString()} daily returns
      </Text>
      <Text variant="caption" as="p">
        Each other version contributes one published primary configuration (its selected grid
        configuration, otherwise its strategy path); each column stands in for this version.{' '}
        {rank.peers.length + 1} compared ({rank.peers.length} other versions + this one) ·{' '}
        {rank.excluded.length} excluded
        {rank.excluded.length ? (
          <InfoTip
            label="Excluded versions"
            content={
              <Stack gap="xs">
                {[...reasons].map(([detail, versions]) => (
                  <span key={detail}>
                    {detail} {versions.join(', ')}
                  </span>
                ))}
              </Stack>
            }
          />
        ) : null}
      </Text>
      <Text variant="caption" as="p">
        Recorded net returns over the same dates; cost and leverage assumptions may differ between
        versions. Colours show relative standing, not profitability.
        <InfoTip label="Rank conventions" content={rank.conventions} />
      </Text>
    </Stack>
  );
}

function RankMatrix({
  query,
  strategyType,
  memoryVersion,
  columns,
  rows,
}: {
  query: UseQueryResult<VersionRank>;
  strategyType: string;
  memoryVersion: string;
  columns: readonly MetricComparisonColumn[];
  rows: readonly MetricComparisonRow[];
}) {
  // Never show ranks that belong to another version.
  const rank =
    query.data?.strategy_type === strategyType && query.data.memory_version === memoryVersion
      ? query.data
      : undefined;
  if (query.error && !rank)
    return <ErrorPanel message={query.error.message} onRetry={() => void query.refetch()} />;
  if (!rank) return <LoadingSkeleton variant="table" count={rows.length} label="Loading ranks" />;
  const { window } = rank;
  if (!window)
    return (
      <EmptyState
        title="Rank unavailable"
        hint={rank.unavailable_reason ?? 'No common comparison window.'}
      />
    );
  return (
    <Stack gap="stack">
      <RankContext rank={{ ...rank, window }} />
      <MetricComparisonTable
        view="rank"
        caption="Performance rank against published versions"
        columns={columns}
        rows={attachMetricRanks(rows, rank)}
        unrankedNote={UNRANKED_NOTE}
        rankValueLabel={`Value ${window.start_mark} to ${window.end}`}
      />
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CategoricalGridSurface({
  strategyType,
  memoryVersion,
  benchmarkSeries,
  baselineSeries,
}: {
  strategyType: string;
  memoryVersion: string;
  benchmarkSeries?: DatasetChartBundleSeries | null;
  baselineSeries?: DatasetChartBundleSeries | null;
}) {
  const [view, setView] = useState<MetricComparisonView>('values');
  const rankQuery = useQuery({
    queryKey: strategyKeys.rank(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionSurfaceRank(strategyType, memoryVersion, signal),
    staleTime: STALE.analysis,
    retry: false,
    enabled: view === 'rank',
  });
  const gridQuery = useQuery({
    queryKey: strategyKeys.grid(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionSurfaceGrid(strategyType, memoryVersion, signal),
    staleTime: STALE.analysis,
    retry: false,
  });
  const grid = gridQuery.data;
  const paths = useQueries({
    queries: (grid?.data ?? []).map((row) => ({
      queryKey: strategyKeys.gridConfiguration(strategyType, memoryVersion, row.config_id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getVersionSurfaceGridConfiguration(strategyType, memoryVersion, row.config_id, signal),
      staleTime: STALE.analysis,
      retry: false,
    })),
  });
  const failed = [gridQuery, ...paths].filter((query) => query.error && !query.data);
  const error = failed[0]?.error;
  if (error)
    return (
      <Section>
        <ErrorPanel
          message={error.message}
          onRetry={() => {
            for (const query of failed) void query.refetch();
          }}
        />
      </Section>
    );
  if (!grid || paths.some((path) => !path.data)) {
    return (
      <Section>
        <LoadingSkeleton variant="chart" />
      </Section>
    );
  }
  const curveCostBps = strategyGridCurveCostBps(strategyType, memoryVersion);
  const columns = grid.data.map((row, index) => ({
    id: row.config_id,
    label:
      typeof row.account_label === 'string'
        ? row.account_label
        : grid.dimensions
            .map((dimension) => {
              const unit = dimension.label.match(/\(([^)]+)\)$/)?.[1];
              return `${String(row[dimension.key])}${unit ? ` ${unit}` : ''}`;
            })
            .join(' · '),
    detail: row.is_control ? 'Control' : row.is_selected ? 'Selected' : undefined,
    description: grid.dimensions
      .map((dimension) => `${dimension.label}: ${String(row[dimension.key])}`)
      .join(' · '),
    color: chartPaletteColor(index),
  }));
  // Each account keeps its own observed coverage: null values are gaps the chart breaks on.
  const gridSeries = columns
    .map((column, index) => ({
      metric: column.id,
      label: column.label,
      axis: 'left' as const,
      points: (paths[index].data?.data ?? []).map((row) => ({
        x: `${row.date.slice(0, 10)}T00:00:00`,
        y: row.selected_portfolio_value,
      })),
    }))
    .filter((_, index) => curveCostBps === null || grid.data[index].cost_bps === curveCostBps);
  // A grid account that is the operator baseline's own run is drawn once, as the baseline.
  const baselineShown = baselineSeries ?? null;
  const series: PortfolioDrawdownChartProps['series'][number][] = baselineShown
    ? [...gridSeries.filter((line) => !duplicatesSeries(baselineShown, [line])), baselineShown]
    : gridSeries;
  const partialCoverage = paths.some((path) => {
    const coverage = path.data?.coverage;
    return coverage !== undefined && coverage.selected.observed_days < coverage.calendar_days;
  });
  if (benchmarkSeries) series.push(benchmarkSeries);
  const rows = buildPerformanceMatrixRows(
    grid,
    Object.fromEntries(
      grid.data.flatMap((row, index) => {
        const metrics = paths[index].data?.metrics.selected;
        return metrics ? [[row.config_id, metrics]] : [];
      }),
    ),
  );
  const orderedColumns = sortColumnsBySortino(columns, rows);
  return (
    <>
      <Section>
        <PortfolioDrawdownChart
          title={`$100 portfolios · ${memoryVersion}`}
          series={series}
          metricColors={{
            ...Object.fromEntries(columns.map((column) => [column.id, column.color])),
            ...(benchmarkSeries ? { [benchmarkSeries.metric]: chartColor('benchmark') } : {}),
            ...(baselineShown ? { [baselineShown.metric]: chartColor('baseline') } : {}),
          }}
        />
        {partialCoverage ? (
          <Text variant="caption" as="p">
            Accounts cover different dates; gaps are unobserved days, not zero returns. Each
            account&apos;s metrics use only its own observed days.
          </Text>
        ) : null}
      </Section>
      <Section
        title="Performance matrix · Sortino ↓"
        actions={
          <SegmentedControl
            size="sm"
            ariaLabel="Performance matrix view"
            options={VIEW_OPTIONS}
            value={view}
            onValueChange={setView}
          />
        }
      >
        {view === 'rank' ? (
          <RankMatrix
            query={rankQuery}
            strategyType={strategyType}
            memoryVersion={memoryVersion}
            columns={orderedColumns}
            rows={rows}
          />
        ) : (
          <MetricComparisonTable columns={orderedColumns} rows={rows} />
        )}
      </Section>
    </>
  );
}
