/**
 * Selected-run composition view: one or more assets' net contribution and portfolio
 * weight, picked from a roster ranked by contribution or weight. The URL owns the picks.
 *
 * USAGE:
 *   <SingleAssetStrategySurface strategyType="family" memoryVersion="v001" assets={['BTC']} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  BrushBar,
  ChartKey,
  ChartState,
  chartKeyItems,
  MultiPaneTimeSeriesChart,
  TimeSeriesChart,
} from '@quant-factory/qf-ui/charts/chrome';
import { useChartBrush } from '@quant-factory/qf-ui/charts/hooks';
import { formatYAxis, LineChart, type QfLineSeries } from '@quant-factory/qf-ui/charts/renderers';
import { chartColor, chartPaletteColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable, type DataTableColumn } from '@quant-factory/qf-ui/tables';
import { useQueries } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { STALE } from '@/lib/api/stale-times';
import {
  getVersionSingleAsset,
  type SingleAssetRanking,
  type SingleAssetView,
  strategyKeys,
} from '@/lib/api/strategies';
import {
  Button,
  EmptyState,
  formatIsoDay,
  formatSignedNumber,
  isLoadingData,
  LoadingSkeleton,
  pluralize,
  SearchSelect,
  Section,
  SelectControl,
  StatGrid,
  StatItem,
  Text,
  Toolbar,
} from '@/ui';
import { CompositionPending } from './CompositionPending';

// --------------------------------------------------------------------------- #
// Public contract
// --------------------------------------------------------------------------- #

export interface SingleAssetStrategySurfaceProps {
  strategyType: string;
  memoryVersion: string;
  selectedRunId: string | null;
  assets: readonly string[];
  configId?: string | null;
  onConfigChange?: (configId: string) => void;
  onAssetsChange: (assets: string[], replace?: boolean) => void;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Picks made when the page opens or the ranking changes. */
const DEFAULT_PICKS = 5;

type RankKey = 'top' | 'bottom' | 'weight' | 'peak' | 'held';

const pp = (value: number) => formatSignedNumber(value, 2, ' pp');
const pct = (value: number) => `${value.toFixed(2)}%`;

const RANKS: Record<
  RankKey,
  { label: string; value: (row: SingleAssetRanking) => number; detail: (value: number) => string }
> = {
  top: { label: 'Top contributors', value: (r) => r.net_contribution_pp, detail: pp },
  bottom: {
    label: 'Bottom contributors',
    value: (r) => -r.net_contribution_pp,
    detail: (v) => pp(-v),
  },
  weight: { label: 'Average weight', value: (r) => r.mean_abs_weight_percent, detail: pct },
  peak: { label: 'Peak weight', value: (r) => r.peak_abs_weight_percent, detail: pct },
  held: { label: 'Time held', value: (r) => r.held_percent, detail: (v) => `${v.toFixed(0)}%` },
};

const RANKING_COLUMNS: DataTableColumn<SingleAssetRanking>[] = [
  { key: 'asset', header: 'Asset', kind: 'identifier' },
  { key: 'net_contribution_pp', header: 'Net contribution (pp)', kind: 'number', digits: 2 },
  { key: 'mean_abs_weight_percent', header: 'Average weight (%)', kind: 'number', digits: 2 },
  { key: 'peak_abs_weight_percent', header: 'Peak weight (%)', kind: 'number', digits: 2 },
  { key: 'held_percent', header: 'Time held (%)', kind: 'number', digits: 0 },
];

type Available = Extract<SingleAssetView, { available: true }>;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SingleAssetStrategySurface({
  strategyType,
  memoryVersion,
  selectedRunId,
  assets,
  configId = null,
  onConfigChange,
  onAssetsChange,
}: SingleAssetStrategySurfaceProps) {
  const [rank, setRank] = useState<RankKey>('top');
  // Nothing picked yet: load the run's default asset, which also carries the ranking.
  const requested = assets.length > 0 ? assets : [null];
  // Everything but the trailing asset slot: the run-level identity a previous pick's
  // payload may still describe while the next one loads.
  const runKey = strategyKeys
    .singleAsset(strategyType, memoryVersion, selectedRunId, null, configId)
    .slice(0, -1);
  const queries = useQueries({
    queries: requested.map((asset, index) => ({
      queryKey: strategyKeys.singleAsset(
        strategyType,
        memoryVersion,
        selectedRunId,
        asset,
        configId,
      ),
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const result = await getVersionSingleAsset(
          strategyType,
          memoryVersion,
          asset,
          signal,
          configId,
        );
        if (
          result.strategy_type !== strategyType ||
          result.memory_version !== memoryVersion ||
          (result.available &&
            ((selectedRunId !== null && result.run_id !== selectedRunId) ||
              (asset !== null && result.asset !== asset) ||
              (configId !== null && result.config_id !== configId)))
        ) {
          throw new Error('The selected result changed. Refresh the page to load its current run.');
        }
        return result;
      },
      // Only the lead pick keeps its previous payload, so the toolbar's run-level facts
      // (configurations, roster, ranking) survive a switch; its curves never paint.
      placeholderData:
        index === 0
          ? (
              previous: SingleAssetView | undefined,
              previousQuery: { queryKey: readonly unknown[] } | undefined,
            ) =>
              previousQuery && runKey.every((part, at) => previousQuery.queryKey[at] === part)
                ? previous
                : undefined
          : undefined,
      staleTime: STALE.list,
      retry: false,
    })),
  });

  const lead = queries[0];
  const stale = queries.some(isLoadingData);
  const failed = queries.find((query) => query.error && query.data === undefined);
  const unavailable = lead?.data && !lead.data.available ? lead.data : null;
  const runSurface = lead?.data?.available ? lead.data : null;
  const surfaces = stale
    ? []
    : queries.flatMap((query) => (query.data?.available ? [query.data] : []));

  const ranking = runSurface?.ranking ?? null;
  const ranked = useMemo(() => {
    if (!ranking) return null;
    const metric = RANKS[rank].value;
    return [...ranking].sort((a, b) => metric(b) - metric(a));
  }, [ranking, rank]);
  const roster = ranked?.map((row) => row.asset) ?? runSurface?.assets ?? [];
  const metricByAsset = useMemo(
    () => new Map(ranked?.map((row) => [row.asset, RANKS[rank].value(row)]) ?? []),
    [ranked, rank],
  );

  // First visit: pick the leaders when the run ranks its assets, else its default asset.
  useEffect(() => {
    if (assets.length > 0 || lead?.isPlaceholderData || !runSurface) return;
    onAssetsChange(
      ranked ? ranked.slice(0, DEFAULT_PICKS).map((row) => row.asset) : [runSurface.asset],
      true,
    );
  }, [assets.length, lead?.isPlaceholderData, onAssetsChange, ranked, runSurface]);

  const changeRank = (next: RankKey) => {
    setRank(next);
    if (!ranking) return;
    const metric = RANKS[next].value;
    onAssetsChange(
      [...ranking]
        .sort((a, b) => metric(b) - metric(a))
        .slice(0, DEFAULT_PICKS)
        .map((row) => row.asset),
    );
  };

  // Until the run first loads, the full loading frame, so the toolbar never grows
  // controls; after that, picks reload under the live toolbar.
  const [runLoaded, setRunLoaded] = useState(false);
  if (runSurface && !runLoaded) setRunLoaded(true);
  if (!runLoaded && lead && lead.data === undefined && lead.isFetching) {
    return <CompositionPending />;
  }

  return (
    <>
      {unavailable ? null : (
        <Section>
          <Toolbar aria-label="Composition controls">
            {ranking ? (
              <SelectControl
                ariaLabel="Rank assets by"
                className="w-full sm:w-52"
                value={rank}
                onValueChange={(value) => changeRank(value as RankKey)}
                options={Object.entries(RANKS).map(([value, item]) => ({
                  value,
                  label: item.label,
                }))}
              />
            ) : null}
            <SearchSelect
              multiple
              label="assets"
              items={roster}
              value={assets}
              onChange={(next) => onAssetsChange(next)}
              detail={
                ranked
                  ? (item) => {
                      const value = metricByAsset.get(item);
                      return value === undefined ? null : RANKS[rank].detail(value);
                    }
                  : undefined
              }
              placeholder="search selected-run assets…"
              className="w-full sm:w-72"
            />
            {runSurface?.configurations && onConfigChange ? (
              <SelectControl
                ariaLabel="Configuration"
                className="w-full sm:w-72"
                value={configId ?? runSurface.config_id}
                onValueChange={onConfigChange}
                options={runSurface.configurations.map((item) => ({
                  value: item.id,
                  label: item.label,
                }))}
              />
            ) : null}
          </Toolbar>
        </Section>
      )}

      <Section>
        {failed?.error ? (
          <TimeSeriesChart title="Composition unavailable">
            <ChartState
              status="error"
              message={failed.error.message}
              action={<Button onClick={() => void failed.refetch()}>Retry</Button>}
            />
          </TimeSeriesChart>
        ) : unavailable ? (
          <EmptyState title="Composition unavailable" hint={unavailable.reason} />
        ) : stale ? (
          <LoadingSkeleton variant="chart" />
        ) : surfaces.length === 0 ? (
          <EmptyState title="Composition unavailable" hint="No selected asset has a composition." />
        ) : (
          <CompositionChart surfaces={surfaces} />
        )}
      </Section>

      {surfaces.length > 0 && ranking ? (
        <Section title="Selected assets">
          <DataTable
            data={surfaces.flatMap(
              (surface) => ranking.find((row) => row.asset === surface.asset) ?? [],
            )}
            columns={RANKING_COLUMNS}
            rowKey={(row) => row.asset}
            maxRows={surfaces.length}
            sortable
          />
        </Section>
      ) : surfaces.length === 1 && surfaces[0] ? (
        <AssetFacts surface={surfaces[0]} />
      ) : null}

      {surfaces[0] ? (
        <Section title="Method">
          <Text as="p" tone="muted" size="sm">
            {surfaces[0].methodology} Observed {formatIsoDay(surfaces[0].first_observed_at)} –{' '}
            {formatIsoDay(surfaces[0].last_observed_at)} · {ledgerSettings(surfaces[0])}.
          </Text>
        </Section>
      ) : null}
    </>
  );
}

// --------------------------------------------------------------------------- #
// Parts
// --------------------------------------------------------------------------- #

function ledgerSettings(surface: Available): string {
  return surface.artifact_contract === 'asset_attribution_v1'
    ? `${surface.cost_bps.toLocaleString()} bps · ${surface.capital_basis === 'rebased_windows' ? 'window-rebased daily holdings' : 'actual daily holdings'}`
    : `${surface.cost_bps.toLocaleString()} bps · every ${surface.rebalance_every_bars} ${pluralize(surface.rebalance_every_bars ?? 0, 'bar')}`;
}

/** One asset adds its price as the benchmark line; several compare contribution and weight. */
function CompositionChart({ surfaces }: { surfaces: readonly Available[] }) {
  // One row per mark across every pick, so a single brush windows all of them.
  const rows = useMemo(() => {
    const byTime = new Map<
      string,
      { date: Date; values: Map<string, Available['data'][number]> }
    >();
    for (const surface of surfaces) {
      for (const row of surface.data) {
        const entry = byTime.get(row.timestamp) ?? {
          date: new Date(row.timestamp),
          values: new Map(),
        };
        entry.values.set(surface.asset, row);
        byTime.set(row.timestamp, entry);
      }
    }
    return [...byTime.values()].sort((a, b) => a.date.getTime() - b.date.getTime());
  }, [surfaces]);
  const brush = useChartBrush(rows);
  const first = rows[0];
  const last = rows.at(-1);
  const domain = brush.xDomain ?? (first && last ? ([first.date, last.date] as const) : undefined);
  const single = surfaces.length === 1 ? surfaces[0] : undefined;
  const colorOf = (index: number) => (single ? chartColor(3) : chartPaletteColor(index));
  const points = (asset: string, field: 'cumulative_contribution_pp' | 'weight_percent') =>
    brush.visibleData.map((row) => ({
      date: row.date,
      value: row.values.get(asset)?.[field] ?? null,
    }));

  const contributionSeries: QfLineSeries[] = [
    ...(single
      ? [
          {
            key: 'price',
            label: 'Price (quote currency)',
            isBenchmark: true,
            color: chartColor('benchmark'),
            valueFormat: 'number' as const,
            points: brush.visibleData.map((row) => ({
              date: row.date,
              value: row.values.get(single.asset)?.price ?? null,
            })),
          },
        ]
      : []),
    ...surfaces.map((surface, index) => ({
      key: `contribution:${surface.asset}`,
      label: single ? 'Cumulative contribution (pp)' : surface.asset,
      axis: 'primary' as const,
      color: colorOf(index),
      valueFormat: (value: number) => formatYAxis(value, 'percentage-points'),
      points: points(surface.asset, 'cumulative_contribution_pp'),
    })),
  ];
  const weightSeries: QfLineSeries[] = surfaces.map((surface, index) => ({
    key: `weight:${surface.asset}`,
    label: single ? 'Weight (%)' : surface.asset,
    interpolation: 'step-end' as const,
    color: single ? chartColor(1) : colorOf(index),
    valueFormat: (value: number) => formatYAxis(value, 'percent-points'),
    points: points(surface.asset, 'weight_percent'),
  }));
  const legend = single ? [...contributionSeries, ...weightSeries] : contributionSeries;

  return (
    <MultiPaneTimeSeriesChart
      title={
        single
          ? `${single.asset} · price, net contribution and portfolio weight`
          : `${surfaces.length} assets · net contribution and portfolio weight`
      }
      linked
      xDomain={domain}
      legend={<ChartKey items={chartKeyItems(legend)} />}
      panes={[
        {
          id: 'performance',
          label: single ? 'Price and cumulative contribution' : 'Cumulative net contribution (pp)',
          content: (
            <LineChart
              height="100%"
              series={contributionSeries}
              ariaLabel={
                single ? 'Asset price and cumulative contribution' : 'Cumulative contribution'
              }
            />
          ),
        },
        {
          id: 'weight',
          label: 'Portfolio weight (%)',
          size: 'study',
          content: (
            <LineChart height="100%" series={weightSeries} ariaLabel="Asset portfolio weight" />
          ),
        },
      ]}
      controls={<BrushBar data={rows} domain={brush.xDomain} onDomainChange={brush.setDomain} />}
    />
  );
}

/** Ledgers without a ranking (ordinary_ledger_v1) keep the single-asset fact strip. */
function AssetFacts({ surface }: { surface: Available }) {
  return (
    <Section title="Asset facts">
      <StatGrid variant="strip" columns={2} boxed aria-label="Single asset facts">
        <StatItem
          label="Peak absolute weight"
          value={`${surface.peak_abs_weight_percent.toFixed(2)}%`}
        />
        <StatItem
          label="Ending contribution"
          value={`${surface.ending_contribution_pp.toFixed(4)} pp`}
          tone={surface.ending_contribution_pp < 0 ? 'critical' : 'default'}
        />
      </StatGrid>
    </Section>
  );
}
