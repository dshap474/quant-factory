/**
 * Dashboard home — recent strategy activity, versioned strategy stats, catalog stats.
 *
 * USAGE:
 *   Routed at /
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { useCatalogStats } from '@/lib/api/catalog';
import { useStrategyTypes } from '@/lib/api/strategies';
import {
  Columns,
  ErrorPanel,
  extentBy,
  formatBytes,
  formatCount,
  formatIsoDay,
  formatNumber,
  isLoadingData,
  LoadingSkeleton,
  PageHeader,
  PageShell,
  PipelineArchitectureMap,
  Section,
  Stack,
  StatCard,
  StatGrid,
  StatItem,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function HomePage() {
  const statsQuery = useCatalogStats();
  const typesQuery = useStrategyTypes();

  const stats = statsQuery.data ?? null;
  const types = typesQuery.data ?? [];
  const statsFailed = statsQuery.data === undefined ? statsQuery.error : null;
  const typesFailed = typesQuery.data === undefined ? typesQuery.error : null;

  const recentStrategies = [...types]
    .sort((a, b) => (b.latest_run ?? '').localeCompare(a.latest_run ?? ''))
    .slice(0, 5);
  const versionCount = types.reduce((sum, type) => sum + type.version_count, 0);
  const runCount = types.reduce((sum, type) => sum + type.total_runs, 0);
  const bestSharpe = extentBy(types, (type) => type.best_sharpe)?.max ?? 0;

  return (
    <PageShell maxWidth="full">
      <PageHeader title="Dashboard Overview" subtitle="quant-factory visualization platform" />

      <Section>
        <PipelineArchitectureMap />
      </Section>

      <Section>
        <Stack gap="heading">
          {isLoadingData(typesQuery) || isLoadingData(statsQuery) ? (
            <LoadingSkeleton variant="card" count={6} />
          ) : (
            <div className="metrics-strip">
              {!typesFailed ? (
                <>
                  <StatCard label="Strategy Types" value={types.length} format="raw" />
                  <StatCard label="Versions" value={versionCount} format="raw" />
                  <StatCard label="Runs" value={runCount} format="raw" />
                  <StatCard
                    label="Best Sharpe"
                    value={bestSharpe}
                    format="number"
                    trend={bestSharpe > 0 ? 'up' : undefined}
                  />
                </>
              ) : null}
              {!statsFailed ? (
                <>
                  <StatCard label="Parquet Files" value={stats?.parquet_files || 0} format="raw" />
                  <StatCard
                    label="Data Size"
                    value={formatBytes((stats?.total_size_mb || 0) * 1024 ** 2, {
                      minUnit: 'MB',
                      maxUnit: 'GB',
                    })}
                    format="raw"
                  />
                </>
              ) : null}
            </div>
          )}
          {statsFailed ? (
            <ErrorPanel
              message={statsFailed.message}
              onRetry={() => {
                void statsQuery.refetch();
              }}
            />
          ) : null}
        </Stack>
      </Section>

      <Columns
        template={stats?.directories ? 'minmax(0,2fr) minmax(0,1fr)' : 'minmax(0,1fr)'}
        from="xl"
        gap="section"
      >
        <Section title="Recent Strategy Activity" className="min-w-0">
          {typesFailed ? (
            <ErrorPanel
              message={typesFailed.message}
              onRetry={() => {
                void typesQuery.refetch();
              }}
            />
          ) : (
            <DataTable
              dense
              rowOffset={0}
              loading={isLoadingData(typesQuery)}
              skeletonRows={5}
              data={recentStrategies.map((type) => ({
                strategy: type.strategy_type,
                versions_runs: `${type.version_count}·${type.total_runs}`,
                sharpe: formatNumber(type.best_sharpe, 2),
                latest: formatIsoDay(type.latest_run),
              }))}
              columns={['strategy', 'versions_runs', 'sharpe', 'latest']}
              emptyTitle="No strategy activity"
              emptyHint="Run a strategy version to see activity here"
            />
          )}
        </Section>

        {stats?.directories ? (
          <Section title="Data Directories" className="min-w-0">
            <StatGrid variant="rows">
              {Object.entries(stats.directories).map(([dir, count]) => (
                <StatItem key={dir} label={`${dir}/`} value={`${formatCount(count)} files`} />
              ))}
            </StatGrid>
          </Section>
        ) : null}
      </Columns>
    </PageShell>
  );
}
