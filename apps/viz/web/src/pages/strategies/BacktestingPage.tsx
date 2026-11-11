/**
 * Backtesting — pick a strategy, version and preset and view that backtest; update it on demand.
 *
 * USAGE:
 *   Routed at /strategies/backtesting?family=example&version=v002&preset=candidate
 *   (the Backtesting tab of Strategies; Overview is the other tab)
 *
 * The chart is growth of $1 for one curve. Update backtest sits in its own row between the
 * picker and the chart. The Preset column offers the version's published
 * backtest and every preset an Update backtest has rerun on the newest inputs; updated curves
 * sit beside the published record, which is never changed. Update backtest starts a background
 * job for every preset of the version (versions with a `rerun.py` only) and the page polls
 * until it finishes. A family whose Viz extension names a `backtestBenchmark` gets it as a
 * dashed grey overlay indexed to the strategy at the left edge of the view.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  BrushBar,
  ChartKey,
  ChartState,
  TimeSeriesChart,
} from '@quant-factory/qf-ui/charts/chrome';
import { useChartBrush } from '@quant-factory/qf-ui/charts/hooks';
import { LineChart, type QfLineSeries } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable } from '@quant-factory/qf-ui/tables';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { strategyBacktestBenchmark } from '@/extensions';
import {
  type BacktestUpdate,
  useBacktestUpdate,
  useBacktestUpdateVersions,
  useStartBacktestUpdate,
} from '@/lib/api/backtest-updates';
import { useBenchmark } from '@/lib/api/benchmarks';
import { STALE } from '@/lib/api/stale-times';
import {
  getVersionSurface,
  type ResearchStrategySurface,
  type StrategyVersionSummary,
  strategyKeys,
  useStrategyTypes,
  useStrategyVersions,
} from '@/lib/api/strategies';
import { compareVersionsDesc } from '@/lib/research-lifecycle';
import {
  Banner,
  Button,
  Cluster,
  ColumnBrowser,
  ErrorPanel,
  formatIsoDay,
  formatLocaleMoney,
  isLoadingData,
  LoadingSkeleton,
  QueryState,
  Section,
  StatGrid,
  StatItem,
  StatusBadge,
} from '@/ui';
import { StrategiesFrame } from './StrategiesFrame';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const PUBLISHED = 'published';
const COLOR = chartColor(1);

type Point = { date: Date; value: number };
type Preset = BacktestUpdate['presets'][number];
type Job = BacktestUpdate['job'];
type SurfaceRow = ResearchStrategySurface['data'][number];
type PerformanceRow = Extract<SurfaceRow, { strategy_portfolio_value: number }>;
type PnlRow = Extract<SurfaceRow, { cumulative_pnl_usd: number }>;

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

/** Versions with a published backtest or a rerun, never invalidated ones, newest first. */
function chartable(
  versions: StrategyVersionSummary[],
  updatable: (version: string) => boolean,
): StrategyVersionSummary[] {
  return versions
    .filter(
      (item) =>
        (item.has_surface || updatable(item.memory_version)) &&
        item.display_state !== 'invalidated',
    )
    .sort(compareVersionsDesc);
}

function growth(rows: Preset['series']): Point[] {
  const first = rows[0]?.nav ?? 1;
  return rows.map((row) => ({ date: new Date(row.timestamp), value: row.nav / first }));
}

/** Account surfaces chart portfolio value; per-trade PnL surfaces chart 1 + PnL / allocation. */
function surfaceGrowth(surface: ResearchStrategySurface): Point[] {
  const performance = surface.data.filter((row): row is PerformanceRow => 'date' in row);
  if (performance.length > 0) {
    const first = performance[0].strategy_portfolio_value;
    return performance.map((row) => ({
      date: new Date(row.date),
      value: row.strategy_portfolio_value / first,
    }));
  }
  const allocation = surface.pnl?.allocation_usd;
  if (!allocation) return [];
  return surface.data
    .filter((row): row is PnlRow => 'timestamp' in row)
    .map((row) => ({
      date: new Date(row.timestamp),
      value: 1 + row.cumulative_pnl_usd / allocation,
    }));
}

/** The family's benchmark as a qf-charts benchmark series; null when it has none. */
function useBenchmarkSeries(family: string): QfLineSeries | null {
  const ticker = strategyBacktestBenchmark(family);
  const query = useBenchmark(ticker ?? '');
  return useMemo(
    () =>
      ticker && query.data
        ? {
            key: 'benchmark',
            label: ticker,
            isBenchmark: true,
            points: query.data.data.map((row) => ({
              date: new Date(row.timestamp),
              value: row.close,
            })),
          }
        : null,
    [query.data, ticker],
  );
}

function jobLabel(job: Job): string | undefined {
  if (!job) return undefined;
  if (job.state === 'running') return `Updating since ${formatIsoDay(job.started_at)}…`;
  if (job.state === 'failed') return `Last update failed: ${job.error ?? 'see job.log'}`;
  return `Last updated ${formatIsoDay(job.finished_at)}`;
}

// --------------------------------------------------------------------------- #
// Chart
// --------------------------------------------------------------------------- #

function GrowthChart({
  title,
  points,
  benchmark,
}: {
  title: string;
  points: Point[];
  /** Overlay on the strategy's scale; never widens the time extent. */
  benchmark?: QfLineSeries | null;
}) {
  const extent = useMemo(() => points.map((point) => ({ date: point.date })), [points]);
  const brush = useChartBrush(extent);
  const domain = brush.xDomain;
  const visible = useMemo(() => {
    const series: QfLineSeries = { key: 'backtest', label: 'Backtest', color: COLOR, points };
    const plotted = benchmark ? [series, benchmark] : [series];
    if (!domain) return plotted;
    const [low, high] = domain.map((date) => date.getTime());
    return plotted.map((item) => ({
      ...item,
      points: item.points.filter(
        (point) => point.date.getTime() >= low && point.date.getTime() <= high,
      ),
    }));
  }, [points, benchmark, domain]);
  // Enough decimals that a near-flat curve's ticks stay distinct (2 at a 0.1× span, 4 at 0.001×).
  const digits = useMemo(() => {
    const values = visible.flatMap((item) =>
      item.points.flatMap((point) => (point.value === null ? [] : [point.value])),
    );
    const span = values.length ? Math.max(...values) - Math.min(...values) : 1;
    return Math.min(4, Math.max(2, 1 - Math.floor(Math.log10(span || 1))));
  }, [visible]);

  return (
    <TimeSeriesChart
      title={benchmark ? `${title} · vs ${benchmark.label}` : title}
      legend={<ChartKey items={[{ id: 'backtest', label: 'Backtest', color: COLOR }]} />}
      controls={<BrushBar data={extent} domain={domain} onDomainChange={brush.setDomain} />}
    >
      {extent.length === 0 ? (
        <ChartState status="empty" message="No backtest curve published" />
      ) : (
        <LineChart
          height="100%"
          series={visible}
          ariaLabel="Backtest growth"
          yFormat={(value) => `${value.toFixed(digits)}×`}
          xDomain={domain}
          benchmarkScale="primary"
        />
      )}
    </TimeSeriesChart>
  );
}

// --------------------------------------------------------------------------- #
// Views: an updated preset, or the published backtest
// --------------------------------------------------------------------------- #

function UpdatedView({
  family,
  version,
  preset,
  runAt,
}: {
  family: string;
  version: string;
  preset: Preset;
  runAt: string | null;
}) {
  const points = useMemo(() => growth(preset.series), [preset]);
  const benchmark = useBenchmarkSeries(family);
  return (
    <>
      <Section>
        <GrowthChart
          title={`${family} ${version} · ${preset.preset} · growth of $1`}
          points={points}
          benchmark={benchmark}
        />
      </Section>
      <Section title="Status">
        <StatGrid variant="strip" columns={4} boxed aria-label="Backtest status">
          <StatItem label="Backtest run" value={formatIsoDay(runAt)} />
          <StatItem label="Updated" value={formatIsoDay(preset.refreshed_at)} />
          <StatItem label="Inputs through" value={formatIsoDay(preset.inputs_end)} />
          <StatItem label="NAV" value={formatLocaleMoney(preset.nav, 0)} />
        </StatGrid>
      </Section>
    </>
  );
}

function PublishedView({
  family,
  version,
  runAt,
}: {
  family: string;
  version: string;
  runAt: string | null;
}) {
  const query = useQuery({
    queryKey: strategyKeys.surface(family, version),
    queryFn: ({ signal }) => getVersionSurface(family, version, signal),
    staleTime: STALE.list,
    retry: false,
  });
  const surface = query.data;
  const benchmark = useBenchmarkSeries(family);
  const points = useMemo(() => (surface ? surfaceGrowth(surface) : []), [surface]);

  if (isLoadingData(query)) return <LoadingSkeleton variant="chart" />;
  if (query.error && !surface) {
    return (
      <TimeSeriesChart title="Published backtest unavailable">
        <ChartState
          status="error"
          message={query.error.message}
          action={<Button onClick={() => void query.refetch()}>Retry</Button>}
        />
      </TimeSeriesChart>
    );
  }
  if (!surface) {
    return (
      <TimeSeriesChart title="Published backtest unavailable">
        <ChartState status="empty" message="No data. Update backtest builds one from its rerun." />
      </TimeSeriesChart>
    );
  }
  return (
    <>
      <Section>
        <GrowthChart
          title={`${family} ${version} · published · growth of $1`}
          points={points}
          benchmark={benchmark}
        />
      </Section>
      <Section title="Status">
        <StatGrid variant="strip" columns={2} boxed aria-label="Backtest status">
          <StatItem label="Backtest run" value={formatIsoDay(runAt)} />
          <StatItem
            label="Backtest through"
            value={formatIsoDay(points.at(-1)?.date.toISOString())}
          />
        </StatGrid>
      </Section>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

export function BacktestingPage() {
  const [params, setParams] = useSearchParams();
  const typesQuery = useStrategyTypes();
  const families = unique((typesQuery.data ?? []).map((item) => item.strategy_type));
  const family = params.get('family') ?? families[0] ?? '';
  const versionInfoQuery = useBacktestUpdateVersions(family);
  const versionInfo = versionInfoQuery.data ?? {};
  const versionsQuery = useStrategyVersions(family);
  const versionsLoading = isLoadingData(versionsQuery) || isLoadingData(versionInfoQuery);
  const versions = chartable(
    versionsQuery.data ?? [],
    (version) => versionInfo[version]?.updatable ?? false,
  );
  const version = params.get('version') ?? versions[0]?.memory_version ?? '';
  const current = versions.find((item) => item.memory_version === version);
  const runAt = versionInfo[version]?.backtest_run_at ?? null;
  const viewQuery = useBacktestUpdate(family, version);
  const view = viewQuery.data;
  const viewLoading = versionsLoading || isLoadingData(viewQuery);
  const presets = view?.presets ?? [];
  const preset = params.get('preset') ?? (presets.length > 0 ? presets[0].preset : PUBLISHED);
  const updated = presets.find((item) => item.preset === preset);
  const update = useStartBacktestUpdate(family, version);
  const running = view?.job?.state === 'running' || update.isPending;
  const status = update.error?.message ?? jobLabel(view?.job ?? null);

  const choose = (next: Record<string, string>) => setParams(next, { replace: true });
  const action = (
    <Cluster gap="stack" wrap={false}>
      <Button
        variant="primary"
        disabled={!view?.updatable || running}
        title={
          view?.updatable
            ? 'Rerun every preset of this version on the newest inputs'
            : 'This version has no rerun.py'
        }
        onClick={() => update.mutate()}
      >
        {running ? 'Updating…' : 'Update backtest'}
      </Button>
      {status ? (
        <StatusBadge
          tone={
            update.error || view?.job?.state === 'failed'
              ? 'critical'
              : running
                ? 'running'
                : 'neutral'
          }
        >
          {status}
        </StatusBadge>
      ) : null}
    </Cluster>
  );

  return (
    <StrategiesFrame>
      <QueryState
        query={typesQuery}
        skeleton="table"
        count={10}
        isEmpty={families.length === 0}
        emptyTitle="No strategies"
      >
        <Section title="Select">
          <ColumnBrowser
            ariaLabel="Strategy, version and preset"
            columns={[
              {
                id: 'family',
                label: 'Strategy',
                value: family,
                onValueChange: (value) => choose({ family: value }),
                options: families.map((value) => ({ value })),
              },
              {
                id: 'version',
                label: 'Version',
                value: version,
                onValueChange: (value) => choose({ family, version: value }),
                options: versionsLoading
                  ? []
                  : versions.map((item) => ({
                      value: item.memory_version,
                      meta: formatIsoDay(versionInfo[item.memory_version]?.backtest_run_at),
                    })),
                emptyLabel: versionsLoading ? '' : 'No published versions',
                disabled: versionsLoading,
              },
              {
                id: 'preset',
                label: 'Preset',
                value: preset,
                onValueChange: (value) => choose({ family, version, preset: value }),
                options: viewLoading
                  ? []
                  : [
                      ...presets.map((item) => ({
                        value: item.preset,
                        meta: `updated ${formatIsoDay(item.refreshed_at)}`,
                      })),
                      { value: PUBLISHED, meta: 'as run' },
                    ],
                emptyLabel: '',
                disabled: viewLoading,
              },
            ]}
          />
        </Section>
        <Section>{action}</Section>
        {viewQuery.error && !view && !viewLoading ? (
          <Banner tone="warning">Backtest updates unavailable: {viewQuery.error.message}</Banner>
        ) : null}
        {viewLoading ? (
          <LoadingSkeleton variant="chart" />
        ) : versionsQuery.error && !versionsQuery.data ? (
          <ErrorPanel
            message={versionsQuery.error.message}
            onRetry={() => void versionsQuery.refetch()}
          />
        ) : updated ? (
          <UpdatedView
            key={`${family}/${version}/${updated.preset}`}
            family={family}
            version={version}
            preset={updated}
            runAt={runAt}
          />
        ) : current ? (
          <PublishedView
            key={`${family}/${version}`}
            family={family}
            version={version}
            runAt={runAt}
          />
        ) : (
          <Section>
            <DataTable
              data={[]}
              emptyTitle="No backtest"
              emptyHint="Pick a version with a published backtest."
            />
          </Section>
        )}
      </QueryState>
    </StrategiesFrame>
  );
}
