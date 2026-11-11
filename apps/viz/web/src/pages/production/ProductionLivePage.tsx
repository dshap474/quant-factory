/**
 * Production / Live — live capital telemetry published by `qf-production publish-projection`.
 *
 * USAGE:
 *   Routed at /production/live?range=30d&metric=pnl_usd
 *   /production/live?family=family-a   (one deployed strategy)
 *
 * The portfolio view leads with the P&L / return / equity chart (aggregate plus one
 * overlay per strategy) under a range and metric control, then the NAV and P&L summary,
 * then one row per declared member; a member row opens that family's view through
 * `?family=`. Until anything is published the API answers 404 and the tab shows an
 * empty state rather than an error; every other failure keeps the normal error state.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChartState, TimeSeriesChart } from '@quant-factory/qf-ui/charts/chrome';
import {
  MultiSeriesTimeChart,
  type MultiSeriesValueFormat,
} from '@quant-factory/qf-ui/charts/renderers';
import { DataTable, type DataTableColumn } from '@quant-factory/qf-ui/tables';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router';
import {
  isProjectionMissing,
  PRODUCTION_METRICS,
  PRODUCTION_RANGES,
  type ProductionMember,
  type ProductionMetric,
  type ProductionMetrics,
  type ProductionOverview,
  type ProductionRange,
  type ProductionSeries,
  type ProductionStrategy,
  useProductionOverview,
  useProductionSeries,
  useProductionStrategy,
  useProductionStrategySeries,
} from '@/lib/api/production';
import {
  Cluster,
  DataList,
  EmptyState,
  ErrorPanel,
  formatIsoDay,
  formatLocaleMoney,
  formatNumber,
  formatPercent,
  formatShortDateTime,
  formatSignedMoney,
  formatSignedPercent,
  isLoadingData,
  LoadingSkeleton,
  type QueryLike,
  Section,
  SegmentedControl,
  SelectControl,
  StatGrid,
  StatItem,
  StatusBadge,
  useSearchParamsPatch,
} from '@/ui';
import { ProductionFrame } from './ProductionFrame';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

/** Family select value for the whole portfolio; never a valid family token. */
const PORTFOLIO = '*';

const RANGE_LABELS: Record<ProductionRange, string> = {
  '1d': '1D',
  '7d': '7D',
  '30d': '30D',
  ytd: 'YTD',
  all: 'All',
};

const METRIC_LABELS: Record<ProductionMetric, string> = {
  pnl_usd: 'P&L',
  return_pct: 'Return',
  equity: 'Equity',
};

const METRIC_FORMATS: Record<ProductionMetric, MultiSeriesValueFormat> = {
  pnl_usd: 'money',
  return_pct: 'percent-delta',
  equity: 'money',
};

export const EMPTY_TITLE = 'No live strategies yet';
export const EMPTY_HINT = 'Live capital appears here once qf-production publish-projection runs.';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function pick<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.find((item) => item === value) ?? fallback;
}

function signedTone(value: number | null | undefined): 'default' | 'critical' {
  return value != null && value < 0 ? 'critical' : 'default';
}

function yesNo(value: unknown): string {
  return value ? 'yes' : 'no';
}

/** One chart line per response line; the aggregate is the portfolio unless a family is set. */
function chartSeries(series: ProductionSeries, portfolioLabel: string) {
  return [series.aggregate, ...series.strategies].map((line, index) => ({
    metric: index === 0 ? 'aggregate' : `family:${line.family ?? index}`,
    axis: 'left' as const,
    label: line.family ?? portfolioLabel,
    points: line.points.map((point) => ({ x: point.day, y: point.value })),
  }));
}

/** Shared performance stats; `null` metrics render as the kit's em dash, never zero. */
function metricItems(metrics: ProductionMetrics): ReactNode {
  return (
    <>
      <StatItem label="Total return" value={formatSignedPercent(metrics.total_return, 2)} />
      <StatItem label="Sharpe" value={formatNumber(metrics.sharpe, 2)} />
      <StatItem label="Max drawdown" value={formatPercent(metrics.max_drawdown, 1)} />
      <StatItem label="Annualized vol" value={formatPercent(metrics.annualized_volatility, 1)} />
    </>
  );
}

// --------------------------------------------------------------------------- #
// Chart
// --------------------------------------------------------------------------- #

function SeriesChart({
  title,
  query,
  metric,
  label,
  controls,
}: {
  title: string;
  query: QueryLike & { data?: ProductionSeries | undefined };
  metric: ProductionMetric;
  label: string;
  controls: ReactNode;
}) {
  if (isLoadingData(query)) {
    return (
      <TimeSeriesChart title={title} controls={controls}>
        <ChartState status="loading" />
      </TimeSeriesChart>
    );
  }
  if (!query.data) {
    return (
      <TimeSeriesChart title={title} controls={controls}>
        <ChartState status="error" message={query.error?.message ?? 'No series'} />
      </TimeSeriesChart>
    );
  }
  const series = chartSeries(query.data, label).filter((line) => line.points.length > 0);
  if (series.length === 0) {
    return (
      <TimeSeriesChart title={title} controls={controls}>
        <ChartState status="empty" message="No observations in this range" />
      </TimeSeriesChart>
    );
  }
  return (
    <MultiSeriesTimeChart
      title={title}
      series={series}
      valueFormat={METRIC_FORMATS[metric]}
      headerRight={controls}
    />
  );
}

/** Overview stats and a table, in place while the snapshot below the chart loads. */
function ViewSkeleton() {
  return (
    <>
      <Section title="Overview">
        <LoadingSkeleton variant="card" count={4} label="Loading snapshot" />
      </Section>
      <Section>
        <LoadingSkeleton variant="table" count={3} announce={false} />
      </Section>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Portfolio view
// --------------------------------------------------------------------------- #

type MemberRow = ProductionMember & { link: string };

const MEMBER_COLUMNS: DataTableColumn<MemberRow>[] = [
  { key: 'family', header: 'Strategy' },
  { key: 'health', header: 'Health', kind: 'status' },
  { key: 'state', header: 'State' },
  { key: 'included', header: 'Included', format: yesNo },
  { key: 'stale', header: 'Stale', format: yesNo },
  { key: 'capital_weight', header: 'Weight', kind: 'percent' },
  { key: 'equity_usd', header: 'Equity', kind: 'money', digits: 0 },
  { key: 'period_pnl_usd', header: 'Period P&L', kind: 'money', digits: 0 },
  { key: 'inception_pnl_usd', header: 'Inception P&L', kind: 'money', digits: 0 },
  {
    key: 'last_observation_at',
    header: 'Last observation',
    format: (value) => formatShortDateTime(value as string | null),
  },
];

function PortfolioView({
  overview,
  range,
  metric,
  controls,
}: {
  overview: ProductionOverview;
  range: ProductionRange;
  metric: ProductionMetric;
  controls: ReactNode;
}) {
  const seriesQuery = useProductionSeries(range, metric);
  const rows: MemberRow[] = overview.members.map((member) => ({
    ...member,
    link: `/production/live?family=${encodeURIComponent(member.family)}`,
  }));
  const missing = overview.missing_families.length;
  return (
    <>
      <Section>
        <SeriesChart
          title={`${overview.portfolio_id} · ${METRIC_LABELS[metric]}`}
          query={seriesQuery}
          metric={metric}
          label="Portfolio"
          controls={controls}
        />
      </Section>

      <Section title="Overview">
        <StatGrid variant="strip" columns={4} boxed aria-label="Portfolio summary">
          <StatItem label="NAV" value={formatLocaleMoney(overview.equity_usd, 0)} />
          <StatItem
            label="Today P&L"
            value={formatSignedMoney(overview.today_pnl_usd, 0)}
            tone={signedTone(overview.today_pnl_usd)}
          />
          <StatItem
            label="Inception P&L"
            value={formatSignedMoney(overview.inception_pnl_usd, 0)}
            tone={signedTone(overview.inception_pnl_usd)}
          />
          <StatItem
            label="Included"
            value={`${overview.included_families.length} of ${overview.members.length}`}
            delta={missing > 0 ? `${missing} missing` : undefined}
            deltaTone="negative"
          />
          {metricItems(overview.metrics)}
        </StatGrid>
      </Section>

      <Section title="Strategies">
        <DataTable
          data={rows}
          columns={MEMBER_COLUMNS}
          linkColumn="family"
          rowKey={(row) => row.family}
          sortable
          emptyTitle="No strategies declared"
          emptyHint="The published portfolio lists no members."
        />
      </Section>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Strategy view
// --------------------------------------------------------------------------- #

type Position = NonNullable<ProductionStrategy['capital']>['positions'][number];
type HealthCheck = ProductionStrategy['health_checks'][number];

const POSITION_COLUMNS: DataTableColumn<Position>[] = [
  { key: 'instrument', header: 'Instrument' },
  { key: 'side', header: 'Side' },
  { key: 'quantity', header: 'Quantity', kind: 'number', digits: 4 },
  { key: 'entry_price', header: 'Entry', kind: 'money' },
  { key: 'current_price', header: 'Mark', kind: 'money' },
  { key: 'market_value_usd', header: 'Market value', kind: 'money', digits: 0 },
  { key: 'unrealized_pnl_usd', header: 'Unrealized P&L', kind: 'money', digits: 0 },
  { key: 'daily_realized_pnl_usd', header: 'Realized today', kind: 'money', digits: 0 },
];

const CHECK_COLUMNS: DataTableColumn<HealthCheck>[] = [
  { key: 'name', header: 'Check' },
  { key: 'state', header: 'State', kind: 'status' },
  { key: 'detail', header: 'Detail' },
];

function StrategyView({
  family,
  range,
  metric,
  controls,
}: {
  family: string;
  range: ProductionRange;
  metric: ProductionMetric;
  controls: ReactNode;
}) {
  const strategyQuery = useProductionStrategy(family);
  const seriesQuery = useProductionStrategySeries(family, range, metric);
  const strategy = strategyQuery.data;
  const chart = (
    <Section>
      <SeriesChart
        title={`${family} · ${METRIC_LABELS[metric]}`}
        query={seriesQuery}
        metric={metric}
        label={family}
        controls={controls}
      />
    </Section>
  );

  if (isLoadingData(strategyQuery)) {
    return (
      <>
        {chart}
        <ViewSkeleton />
      </>
    );
  }
  if (!strategy && isProjectionMissing(strategyQuery.error)) {
    return (
      <Section>
        <EmptyState
          title={`No live snapshot for ${family}`}
          hint="The production projection publishes no snapshot for this strategy."
        />
      </Section>
    );
  }
  if (!strategy) {
    return (
      <ErrorPanel
        message={strategyQuery.error?.message ?? 'No snapshot'}
        onRetry={() => void strategyQuery.refetch()}
      />
    );
  }

  const capital = strategy.capital;
  const { deployment, authority_facts: authority, last_run: lastRun } = strategy;
  return (
    <>
      {chart}

      <Section title="Overview">
        <StatGrid variant="strip" columns={4} boxed aria-label="Strategy summary">
          <StatItem label="Equity" value={formatLocaleMoney(capital?.equity_usd, 0)} />
          <StatItem
            label="Today P&L"
            value={formatSignedMoney(strategy.today_pnl_usd, 0)}
            tone={signedTone(strategy.today_pnl_usd)}
          />
          <StatItem
            label="Inception P&L"
            value={formatSignedMoney(strategy.inception_pnl_usd, 0)}
            tone={signedTone(strategy.inception_pnl_usd)}
          />
          <StatItem
            label="Gross exposure"
            value={formatLocaleMoney(capital?.gross_exposure_usd, 0)}
          />
          {metricItems(strategy.metrics)}
        </StatGrid>
      </Section>

      <Section title="Positions">
        <DataTable
          data={capital?.positions ?? []}
          columns={POSITION_COLUMNS}
          rowKey={(row) => `${row.instrument}/${row.side}`}
          emptyTitle="No open positions"
          emptyHint={
            capital ? `As of ${formatShortDateTime(capital.as_of)}` : 'No account snapshot yet.'
          }
        />
      </Section>

      <Section title="Health checks">
        <DataTable
          data={strategy.health_checks}
          columns={CHECK_COLUMNS}
          rowKey={(row) => row.name}
          emptyTitle="No health checks reported"
        />
      </Section>

      <Section title="Deployment">
        <DataList
          orientation="horizontal"
          divided
          items={[
            { label: 'Version', value: `${deployment.memory_version} · ${deployment.preset}` },
            { label: 'Venue', value: `${deployment.venue} · ${deployment.instrument}` },
            { label: 'Schedule', value: `${deployment.schedule} (${deployment.timezone})` },
            { label: 'Host', value: `${deployment.host_alias} · ${deployment.host_region}` },
            { label: 'Activation', value: authority.activation_state },
            { label: 'Can trade', value: yesNo(authority.can_trade) },
            {
              label: 'Gates',
              value: `venue ${authority.venue_gate} · capital ${authority.capital_gate}`,
            },
            {
              label: 'Last run',
              value: `${lastRun.result}${lastRun.mode ? ` · ${lastRun.mode}` : ''} · ${formatShortDateTime(lastRun.at)}`,
            },
          ]}
        />
      </Section>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

export function ProductionLivePage() {
  const [params] = useSearchParams();
  const patchParams = useSearchParamsPatch();
  const overviewQuery = useProductionOverview();
  const overview = overviewQuery.data;
  const family = params.get('family') ?? '';
  const range = pick(params.get('range'), PRODUCTION_RANGES, '30d');
  const metric = pick(params.get('metric'), PRODUCTION_METRICS, 'pnl_usd');

  const update = (key: string, value: string | null) =>
    patchParams({ [key]: value }, { replace: true });

  const families = overview?.members.map((member) => member.family) ?? [];
  const controls = (
    <Cluster gap="stack">
      <SelectControl
        size="sm"
        ariaLabel="Strategy"
        value={family || PORTFOLIO}
        onValueChange={(value) => update('family', value === PORTFOLIO ? null : value)}
        options={[
          { value: PORTFOLIO, label: 'Portfolio' },
          ...families.map((value) => ({ value, label: value })),
        ]}
      />
      <SegmentedControl
        size="sm"
        ariaLabel="Series metric"
        value={metric}
        onValueChange={(value) => update('metric', value)}
        options={PRODUCTION_METRICS.map((value) => ({ value, label: METRIC_LABELS[value] }))}
      />
      <SegmentedControl
        size="sm"
        ariaLabel="Series range"
        value={range}
        onValueChange={(value) => update('range', value)}
        options={PRODUCTION_RANGES.map((value) => ({ value, label: RANGE_LABELS[value] }))}
      />
    </Cluster>
  );

  let body: ReactNode;
  if (isLoadingData(overviewQuery)) {
    body = (
      <>
        <Section>
          <TimeSeriesChart
            title={`${family || 'Portfolio'} · ${METRIC_LABELS[metric]}`}
            controls={controls}
          >
            <ChartState status="loading" />
          </TimeSeriesChart>
        </Section>
        <ViewSkeleton />
      </>
    );
  } else if (!overview && isProjectionMissing(overviewQuery.error)) {
    body = (
      <Section>
        <EmptyState title={EMPTY_TITLE} hint={EMPTY_HINT} />
      </Section>
    );
  } else if (!overview) {
    body = (
      <ErrorPanel
        message={overviewQuery.error?.message ?? 'No overview'}
        onRetry={() => void overviewQuery.refetch()}
      />
    );
  } else if (family) {
    body = (
      <StrategyView
        key={family}
        family={family}
        range={range}
        metric={metric}
        controls={controls}
      />
    );
  } else {
    body = <PortfolioView overview={overview} range={range} metric={metric} controls={controls} />;
  }

  return (
    <ProductionFrame
      badges={
        overview ? (
          <Cluster gap="stack">
            <StatusBadge status={overview.completeness} bordered>
              {overview.completeness}
            </StatusBadge>
            <StatusBadge tone="neutral" dot={false}>
              {`as of ${formatIsoDay(overview.generated_at)}`}
            </StatusBadge>
          </Cluster>
        ) : null
      }
    >
      {body}
    </ProductionFrame>
  );
}
