/**
 * One backtest run: header facts (state, engine, duration, data range), then a scrubbable
 * replay whose charts draw only the history up to the cursor (equity/drawdown, one picked
 * held asset's price with its buy and sell arrows and the position's P&L, positions), the
 * KPIs at the cursor and the rebalances up to it, then the run's telemetry, final metrics
 * and config.
 * When the run's family serves it, each rebalance date opens that day worked intraday.
 *
 * USAGE:
 *   Routed at /backtest-engine/runs/:family/:version/:preset/:runId.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChartKey, chartKeyItems, TimeSeriesChart } from '@quant-factory/qf-ui/charts/chrome';
import {
  LineChart,
  PortfolioDrawdownChart,
  type QfLineMark,
  type QfLineSeries,
  StackedTimeChart,
} from '@quant-factory/qf-ui/charts/renderers';
import { chartColor, chartPaletteColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable } from '@quant-factory/qf-ui/tables';
import { ArrowLeft } from 'lucide-react';
import { type ReactNode, useDeferredValue, useMemo, useState } from 'react';
import { useParams } from 'react-router';
import {
  type BacktestReplay,
  type BacktestRun,
  type BacktestRunDetail,
  executionDayHref,
  useBacktestAsset,
  useBacktestEngineRun,
} from '@/lib/api/backtestEngine';
import {
  Badge,
  Button,
  Cluster,
  CodeBlock,
  DataList,
  type DataListEntry,
  EmptyState,
  ErrorPanel,
  formatDuration,
  formatIsoDay,
  formatLocaleMoney,
  formatLocalePrice,
  formatNumber,
  formatPercent,
  formatShortDateTime,
  formatSignedPercent,
  humanize,
  isLoadingData,
  Link,
  LoadingSkeleton,
  PlaybackScrubber,
  SearchSelect,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  TerminalPage,
  TerminalSection,
} from '@/ui';
import { priceDigits, RunStateBadge } from './runs';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const MAX_TRADE_ROWS = 200;
const CASH_COLOR = chartColor('neutral');
const PRICE_COLOR = chartPaletteColor(0);
const PNL_COLOR = chartPaletteColor(1);
const BUY_COLOR = chartColor('positive');
const SELL_COLOR = chartColor('negative');

/** `values` up to and including row `last`, null after it: the chart draws no future. */
function upTo<T>(values: readonly (T | null)[], last: number): (T | null)[] {
  return values.map((value, i) => (i <= last ? (value ?? null) : null));
}

// --------------------------------------------------------------------------- #
// Held asset
// --------------------------------------------------------------------------- #

/**
 * One held asset, picked from the run's roster (largest mean holding first): its price with a
 * green arrow per buy and a red one per sell, and the position's cumulative P&L on the right
 * axis, drawn up to `end`.
 */
function HeldAsset({
  run,
  assets,
  xDomain,
  end,
}: {
  run: BacktestRun;
  assets: string[];
  xDomain: [Date, Date];
  end: Date | undefined;
}) {
  const [asset, setAsset] = useState<string | null>(assets[0] ?? null);
  // Log applies to the price axis only; the P&L axis stays linear (it crosses zero).
  const [logPrice, setLogPrice] = useState(true);
  const query = useBacktestAsset(
    { family: run.family, version: run.version, preset: run.preset, runId: run.run_id },
    asset,
  );
  const data = query.data;
  const parsed = useMemo(
    () =>
      data && {
        dates: data.timestamp.map((value) => new Date(value)),
        marks: data.trades.flatMap((trade): QfLineMark[] =>
          trade.price === null
            ? []
            : [
                {
                  date: new Date(trade.timestamp),
                  value: trade.price,
                  side: trade.delta > 0 ? 'buy' : 'sell',
                },
              ],
        ),
      },
    [data],
  );
  const shown = parsed && end ? parsed.dates.filter((date) => date <= end).length - 1 : -1;
  const series = useMemo<QfLineSeries[]>(() => {
    if (!data || !parsed) return [];
    const points = (values: (number | null)[]) =>
      upTo(values, shown).map((value, i) => ({ date: parsed.dates[i] as Date, value }));
    return [
      {
        key: 'price',
        label: `${data.asset} price`,
        color: PRICE_COLOR,
        points: points(data.price),
        marks: end ? parsed.marks.filter((mark) => mark.date <= end) : [],
      },
      {
        key: 'pnl',
        label: 'Position P&L',
        color: PNL_COLOR,
        axis: 'secondary',
        points: points(data.pnl),
      },
    ];
  }, [data, end, parsed, shown]);
  const pnl = data?.pnl[shown] ?? null;
  const digits = priceDigits(data?.price.find((value) => value !== null));
  return (
    <TimeSeriesChart
      title={
        asset && pnl !== null
          ? `${asset} · position P&L ${formatLocaleMoney(pnl, 0)}`
          : 'Held asset'
      }
      headerRight={
        <Cluster gap="xs" align="center">
          <Button
            type="button"
            variant="control"
            aria-pressed={logPrice}
            title="Log scale for the price axis"
            onClick={() => setLogPrice(!logPrice)}
          >
            Log
          </Button>
          <SearchSelect
            label="asset"
            items={assets}
            value={asset}
            onChange={(next) => next && setAsset(next)}
            placeholder="search held assets…"
          />
        </Cluster>
      }
      legend={
        <ChartKey
          items={[
            { id: 'price', label: 'Price', color: PRICE_COLOR },
            { id: 'pnl', label: 'Position P&L', color: PNL_COLOR },
            { id: 'buy', label: 'Buy', color: BUY_COLOR },
            { id: 'sell', label: 'Sell', color: SELL_COLOR },
          ]}
        />
      }
    >
      {data ? (
        <LineChart
          height="100%"
          ariaLabel={`${data.asset} price with buy and sell arrows, and the position's cumulative P&L`}
          series={series}
          xDomain={xDomain}
          yScaleType={logPrice ? 'log' : 'linear'}
          yFormat={(value) => formatLocalePrice(value, digits)}
          ySecondaryFormat={(value) => formatLocaleMoney(value, 0)}
        />
      ) : query.isError ? (
        <ErrorPanel message={query.error.message} onRetry={() => void query.refetch()} />
      ) : (
        <LoadingSkeleton variant="chart" label={`Loading ${asset ?? 'asset'}`} />
      )}
    </TimeSeriesChart>
  );
}

// --------------------------------------------------------------------------- #
// Replay
// --------------------------------------------------------------------------- #

function Replay({
  replay,
  dayRun,
  assetRun,
}: {
  replay: BacktestReplay;
  dayRun: BacktestRun | null;
  assetRun: BacktestRun | null;
}) {
  const { equity, positions } = replay;
  const dates = useMemo(() => equity.timestamp.map((value) => new Date(value)), [equity]);
  const last = dates.length - 1;
  const [index, setIndex] = useState(last);
  // Charts follow the cursor a frame behind so playback never blocks the slider.
  const chartIndex = useDeferredValue(index);
  const at = equity.timestamp[index] ?? '';

  const portfolios = useMemo(() => {
    const points = (values: (number | null)[]) =>
      upTo(values, chartIndex).map((y, i) => ({ x: equity.timestamp[i] ?? '', y }));
    return [
      {
        metric: 'strategy',
        axis: 'left' as const,
        label: 'Strategy',
        points: points(equity.equity),
      },
      ...(equity.benchmark_equity.some((value) => value !== null)
        ? [
            {
              metric: 'benchmark',
              axis: 'left' as const,
              label: 'Benchmark',
              isBenchmark: true,
              points: points(equity.benchmark_equity),
            },
          ]
        : []),
    ];
  }, [equity, chartIndex]);

  const stacked = useMemo(
    () =>
      positions.assets.map((asset, i) => ({
        key: asset,
        label: asset,
        kind: 'area' as const,
        stack: 'weights',
        step: true,
        color: asset === 'CASH' ? CASH_COLOR : chartPaletteColor(i),
        values: upTo(positions.weights[asset] ?? [], chartIndex),
      })),
    [positions, chartIndex],
  );
  const xDomain = useMemo(() => [dates[0], dates.at(-1)] as [Date, Date], [dates]);

  // Full-history drawdown from the API: display sampling can drop the peak a recompute needs.
  const drawdowns = useMemo(
    () => ({
      strategy: upTo(equity.drawdown, chartIndex).map((y, i) => ({
        x: equity.timestamp[i] ?? '',
        y,
      })),
    }),
    [equity, chartIndex],
  );

  const trades = useMemo(
    () => replay.trades.filter((trade) => trade.timestamp <= at),
    [replay, at],
  );
  // The API keeps the newest trades; before the oldest kept one the table cannot show the rest.
  const oldestKept = replay.trades.at(-1)?.timestamp;
  const tradesCut =
    replay.total_trades > replay.trades.length && oldestKept !== undefined && at < oldestKept;

  return (
    // The bar is the outer stack's first child, so it stays pinned over every section the
    // cursor drives (charts, KPIs, rebalances) and scrolls away with the last of them.
    <Stack gap="section">
      <PlaybackScrubber
        sticky
        ariaLabel="Replay position"
        count={dates.length}
        index={index}
        onIndexChange={setIndex}
        label={formatIsoDay(at)}
      />
      <TerminalSection title="Replay">
        <Stack gap="block">
          <PortfolioDrawdownChart
            title="Equity vs benchmark"
            series={portfolios}
            drawdowns={drawdowns}
          />
          {assetRun && replay.held_assets.length ? (
            <HeldAsset
              run={assetRun}
              assets={replay.held_assets}
              xDomain={xDomain}
              end={dates[chartIndex]}
            />
          ) : null}
          {!replay.weights_known ? (
            <EmptyState
              title="Positions not recorded"
              hint="This run sets quantity targets, so its saved files hold no weights; equity and drawdown are exact."
            />
          ) : stacked.length ? (
            <TimeSeriesChart
              title="Positions · target weights"
              legend={<ChartKey items={chartKeyItems(stacked)} />}
            >
              <StackedTimeChart
                height="100%"
                ariaLabel="Target weights over time"
                dates={dates}
                series={stacked}
                yFormat={(value) => formatPercent(value, 0)}
                onDateClick={(_date, i) => setIndex(i)}
              />
            </TimeSeriesChart>
          ) : null}
        </Stack>
      </TerminalSection>
      <TerminalSection title="At cursor">
        <StatGrid variant="strip" boxed aria-label="Run state at the cursor">
          <StatItem label="Equity" value={formatLocaleMoney(equity.equity[index], 0)} />
          <StatItem
            label="Return to date"
            value={formatSignedPercent(equity.return_to_date[index])}
            tone={(equity.return_to_date[index] ?? 0) < 0 ? 'critical' : 'default'}
          />
          <StatItem label="Drawdown" value={formatPercent(equity.drawdown[index])} />
          <StatItem label="Gross exposure" value={formatPercent(equity.gross_exposure[index])} />
          <StatItem label="Net exposure" value={formatPercent(equity.net_exposure[index])} />
        </StatGrid>
      </TerminalSection>
      <TerminalSection title={tradesCut ? 'Rebalances' : `Rebalances · ${trades.length} to date`}>
        <DataTable
          dense
          data={trades.slice(0, MAX_TRADE_ROWS)}
          rowKey={(trade) => `${trade.timestamp}/${trade.asset}`}
          columns={[
            {
              key: 'timestamp',
              header: 'Date',
              format: (value) => formatIsoDay(String(value)),
              ...(dayRun
                ? {
                    render: (value: unknown, trade: BacktestReplay['trades'][number]) => {
                      const day = formatIsoDay(String(value));
                      return (
                        <Link
                          to={`${executionDayHref(dayRun, day)}?asset=${encodeURIComponent(trade.asset)}`}
                          title="Open the day worked intraday"
                        >
                          {day}
                        </Link>
                      );
                    },
                  }
                : {}),
            },
            { key: 'asset', header: 'Asset' },
            { key: 'from_weight', header: 'From', kind: 'percent' },
            { key: 'to_weight', header: 'To', kind: 'percent' },
            { key: 'delta', header: 'Change', kind: 'percent' },
          ]}
          emptyTitle={
            !replay.weights_known
              ? 'Rebalances not recorded'
              : tradesCut
                ? 'Older rebalances not loaded'
                : 'No rebalances yet'
          }
          emptyHint={
            !replay.weights_known
              ? 'This run sets quantity targets.'
              : tradesCut
                ? `Only the latest ${replay.trades.length} of ${replay.total_trades} are loaded.`
                : 'Move the cursor later in the run.'
          }
        />
      </TerminalSection>
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Run sections
// --------------------------------------------------------------------------- #

/** The run's telemetry facts: phases, size, data window, process and error. */
function runFacts(run: BacktestRun): DataListEntry[] {
  return [
    ...Object.entries(run.phases).map(([phase, seconds]) => ({
      id: `phase-${phase}`,
      label: humanize(phase),
      value: formatDuration(seconds, { belowOneSecond: `${seconds.toFixed(2)}s` }),
      numeric: true,
    })),
    { label: 'Equity rows', value: run.rows ?? '—', numeric: true },
    { label: 'Assets', value: run.assets ?? '—', numeric: true },
    {
      label: 'Data range',
      value: run.data_range
        ? `${formatIsoDay(run.data_range.start)} → ${formatIsoDay(run.data_range.end)}`
        : '—',
    },
    { label: 'Host · pid', value: run.host ? `${run.host} · ${run.pid ?? '—'}` : '—' },
  ];
}

function RunBody({ detail }: { detail: BacktestRunDetail }) {
  const { status, meta, replay } = detail;
  const metrics = Object.entries(status.metrics);
  const config = meta?.config;
  return (
    <Stack gap="section">
      {status.error ? <StateMessage state="error">{status.error}</StateMessage> : null}
      {replay ? (
        <Replay
          replay={replay}
          dayRun={detail.execution ? status : null}
          assetRun={detail.assets ? status : null}
        />
      ) : (
        <EmptyState
          title={status.state === 'running' ? 'Run in progress' : 'No replay for this run'}
          hint={
            status.state === 'running'
              ? 'The replay appears when the run saves its backtest.'
              : 'The run saved no backtest.'
          }
        />
      )}
      <TerminalSection title="Telemetry">
        <DataList orientation="horizontal" items={runFacts(status)} />
      </TerminalSection>
      {metrics.length ? (
        <TerminalSection title="Final metrics">
          <DataList
            orientation="horizontal"
            items={metrics.map(([name, value]) => ({
              label: humanize(name),
              value: formatNumber(value, 4),
              numeric: true,
            }))}
          />
        </TerminalSection>
      ) : null}
      {config ? (
        <TerminalSection title="Config">
          <CodeBlock value={JSON.stringify(config, null, 2)} />
        </TerminalSection>
      ) : null}
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

const BACK_HREF = '/backtest-engine';

/** Icon link back to the run list, set before the page title. */
const back: ReactNode = (
  <Link
    to={BACK_HREF}
    variant="control"
    size="sm"
    icon
    aria-label="Back to backtests"
    title="Back to backtests"
  >
    <ArrowLeft aria-hidden="true" />
  </Link>
);

/** The run id's trailing hash ("…-v002-1a2b3c4d" -> "1a2b3c4d"); the full id is the tooltip. */
function shortRunId(runId: string): string {
  return runId.split('-').at(-1) || runId;
}

export function BacktestRunPage() {
  const { family = '', version = '', preset = '', runId = '' } = useParams();
  const query = useBacktestEngineRun({ family, version, preset, runId });
  const detail = query.data;
  const title = `${family} / ${version} / ${preset}`;
  const runLabel = <span title={runId}>{`run ${shortRunId(runId)}`}</span>;

  if (isLoadingData(query)) {
    return (
      <TerminalPage title={title} subtitle={runLabel} back={back}>
        <Stack gap="section">
          <LoadingSkeleton variant="segmented" label="Loading run" />
          <LoadingSkeleton variant="chart" announce={false} />
          <LoadingSkeleton variant="card" count={5} announce={false} />
        </Stack>
      </TerminalPage>
    );
  }
  if (!detail) {
    return (
      <TerminalPage title={title} subtitle={runLabel} back={back}>
        <ErrorPanel
          message={query.error?.message ?? `Run ${runId} is unavailable.`}
          onRetry={() => void query.refetch()}
        />
      </TerminalPage>
    );
  }
  const { status } = detail;
  // One quiet line under the title: run hash, when it ran and how long it took.
  const when =
    status.state === 'running'
      ? `started ${formatShortDateTime(status.started_at)}`
      : status.finished_at
        ? formatShortDateTime(status.finished_at)
        : null;
  const took =
    status.state !== 'running' && status.duration_s !== null
      ? formatDuration(status.duration_s)
      : null;
  return (
    <TerminalPage
      title={title}
      back={back}
      subtitle={
        <>
          {runLabel}
          {[when, took].filter(Boolean).map((part) => ` · ${part}`)}
        </>
      }
      badges={<RunStateBadge state={status.state} />}
      right={
        <Cluster gap="stack">
          {status.data_range ? (
            <Badge variant="ghost">
              {`${formatIsoDay(status.data_range.start)} → ${formatIsoDay(status.data_range.end)}`}
            </Badge>
          ) : null}
          {status.engine ? <Badge variant="ghost">{status.engine}</Badge> : null}
        </Cluster>
      }
    >
      <RunBody detail={detail} />
    </TerminalPage>
  );
}
