/**
 * One rebalance day worked intraday: the run's parent orders for that day simulated over the
 * day's 1-minute bars under each execution policy. Leads with the dollars still to trade per
 * policy (buys above zero, sells below), then each policy's running cost against trading the
 * whole book at arrival, then one asset's trades for one policy (fills sized by quantity, solid
 * maker / hollow taker, the running average fill against arrival, volume beneath), then cost per
 * policy, the orders, and the assumptions.
 *
 * USAGE:
 *   Routed at /backtest-engine/runs/:family/:version/:preset/:runId/execution/:day[?asset=BTC];
 *   the run page's Rebalances dates link here when the run's family serves the view.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChartKey, chartKeyItems, TimeSeriesChart } from '@quant-factory/qf-ui/charts/chrome';
import {
  LineChart,
  type MarketCandle,
  PriceProfileChart,
  type QfLineSeries,
} from '@quant-factory/qf-ui/charts/renderers';
import { chartColor, chartPaletteColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable } from '@quant-factory/qf-ui/tables';
import { useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import {
  type BacktestRunKey,
  type ExecutionAsset,
  type ExecutionDay,
  runHref,
  useBacktestExecutionAsset,
  useBacktestExecutionDay,
} from '@/lib/api/backtestEngine';
import {
  Badge,
  ChartGrid,
  Cluster,
  ErrorPanel,
  formatLocaleMoney,
  formatLocalePrice,
  formatPercent,
  humanize,
  isLoadingData,
  Link,
  LoadingSkeleton,
  SegmentedControl,
  Stack,
  TerminalPage,
  TerminalSection,
  Text,
} from '@/ui';
import { priceDigits } from './runs';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

type ExecutionOrder = ExecutionDay['orders'][number];

const BUY_COLOR = chartColor('positive');
const SELL_COLOR = chartColor('negative');
const NET_COLOR = chartColor('neutral');
const MINUTE_MS = 60_000;

const money = (value: number) => formatLocaleMoney(value, 0);

function policyColors(day: ExecutionDay): Record<string, string> {
  return Object.fromEntries(day.policies.map((policy, i) => [policy.name, chartPaletteColor(i)]));
}

// --------------------------------------------------------------------------- #
// Whole-book charts
// --------------------------------------------------------------------------- #

/** Dollars still to buy (above zero) and sell (below) per policy, on one shared scale. */
function CapitalInTransit({ day, dates }: { day: ExecutionDay; dates: Date[] }) {
  const charts = useMemo(() => {
    const paths = Object.values(day.book);
    const yDomain = [
      Math.min(0, ...paths.flatMap((path) => path.to_sell)),
      Math.max(0, ...paths.flatMap((path) => path.to_buy)),
    ] as const;
    const points = (values: number[]) =>
      dates.map((date, i) => ({ date, value: values[i] ?? null }));
    const step = { interpolation: 'step-end' as const };
    const area = { ...step, area: true, areaBaseline: 'zero' as const };
    return day.policies.map((policy) => {
      const path = day.book[policy.name] ?? { to_buy: [], to_sell: [], cost: [] };
      const series: QfLineSeries[] = [
        {
          key: 'to_buy',
          label: 'Still to buy',
          color: BUY_COLOR,
          ...area,
          points: points(path.to_buy),
        },
        {
          key: 'to_sell',
          label: 'Still to sell',
          color: SELL_COLOR,
          ...area,
          points: points(path.to_sell),
        },
        {
          key: 'net',
          label: 'Net',
          color: NET_COLOR,
          ...step,
          points: points(path.to_buy.map((value, i) => value + (path.to_sell[i] ?? 0))),
        },
      ];
      return { name: policy.name, series, yDomain };
    });
  }, [day, dates]);
  const xDomain = [dates[0] ?? new Date(), dates.at(-1) ?? new Date()] as const;
  const legend = (
    <ChartKey
      items={[
        { id: 'to_buy', label: 'Still to buy', color: BUY_COLOR },
        { id: 'to_sell', label: 'Still to sell', color: SELL_COLOR },
        { id: 'net', label: 'Net', color: NET_COLOR },
      ]}
    />
  );
  return (
    <ChartGrid columns={2}>
      {charts.map((chart) => (
        <TimeSeriesChart key={chart.name} title={humanize(chart.name)} legend={legend}>
          <LineChart
            height="100%"
            ariaLabel={`${humanize(chart.name)}: dollars still to buy and sell`}
            series={chart.series}
            xDomain={xDomain}
            yDomain={chart.yDomain}
            yFormat={money}
            timeZone="local"
          />
        </TimeSeriesChart>
      ))}
    </ChartGrid>
  );
}

/** Each policy's cost so far against trading the whole book at arrival; ends at its total. */
function RunningCost({ day, dates }: { day: ExecutionDay; dates: Date[] }) {
  const series = useMemo(() => {
    const colors = policyColors(day);
    return day.policies.map((policy) => ({
      key: policy.name,
      label: humanize(policy.name),
      color: colors[policy.name] ?? NET_COLOR,
      interpolation: 'step-end' as const,
      points: dates.map((date, i) => ({ date, value: day.book[policy.name]?.cost[i] ?? null })),
    }));
  }, [day, dates]);
  return (
    <TimeSeriesChart
      title="Cost against trading everything at arrival"
      legend={<ChartKey items={chartKeyItems(series)} />}
    >
      <LineChart
        height="100%"
        ariaLabel="Running execution cost per policy, dollars"
        series={series}
        yFormat={money}
        timeZone="local"
      />
    </TimeSeriesChart>
  );
}

// --------------------------------------------------------------------------- #
// Asset view
// --------------------------------------------------------------------------- #

/** Fill markers and the running average-fill level for one policy's fills. */
function fillLayers(
  fills: ExecutionAsset['fills'][string] | undefined,
  label: string,
  color: string,
  end: number,
) {
  if (!fills?.time_ms.length) return { fills: undefined, levels: [] };
  return {
    fills: {
      key: 'fills',
      label: `${label} fills (solid maker, hollow taker)`,
      color,
      points: fills.time_ms.map((time, i) => ({
        time,
        price: fills.price[i] ?? 0,
        size: fills.quantity[i] ?? 0,
        solid: fills.maker[i] ?? false,
      })),
    },
    levels: [
      {
        key: 'avg_fill',
        label: 'Average fill',
        color,
        style: 'dashed' as const,
        interpolation: 'step-end' as const,
        // Held from the last fill to the end of the day.
        points: [
          ...fills.time_ms.map((time, i) => [time, fills.avg_price[i] ?? null] as const),
          [end, fills.avg_price.at(-1) ?? null] as const,
        ],
      },
    ],
  };
}

function AssetChart({
  day,
  order,
  data,
}: {
  day: ExecutionDay;
  order: ExecutionOrder;
  data: ExecutionAsset;
}) {
  const withFills = day.policies.filter((p) => data.fills[p.name]?.time_ms.length);
  const [chosen, setChosen] = useState<string | null>(null);
  const policy = withFills.find((p) => p.name === chosen)?.name ?? withFills[0]?.name ?? '';
  const color = policyColors(day)[policy] ?? NET_COLOR;
  const label = humanize(policy);
  const fills = data.fills[policy];
  const arrival = order.arrival_mid;
  const start = data.start_ms;
  const end = start + (data.close.length - 1) * MINUTE_MS;

  const minutes = useMemo(() => {
    const price = data.close.map((value, i) => [start + i * MINUTE_MS, value] as const);
    const bars: MarketCandle[] = [];
    data.close.forEach((close, i) => {
      if (close === null) return;
      const time = start + i * MINUTE_MS;
      bars.push({
        time,
        open: close,
        high: close,
        low: close,
        close,
        volume: data.volume[i] ?? 0,
        availableTime: time + MINUTE_MS,
        duration: MINUTE_MS,
      });
    });
    return { price, volume: { label: 'Volume', bars } };
  }, [data, start]);

  const layers = fillLayers(fills, label, color, end);

  const digits = priceDigits(arrival);
  return (
    <PriceProfileChart
      title={`${order.asset} · ${label} fills`}
      ariaLabel={`${order.asset} one-minute close with ${label} fills and running average fill`}
      headerRight={
        withFills.length > 1 ? (
          <SegmentedControl
            size="sm"
            ariaLabel="Policy"
            value={policy}
            onValueChange={setChosen}
            options={withFills.map((p) => ({ value: p.name, label: humanize(p.name) }))}
          />
        ) : null
      }
      xDomain={[start, end]}
      price={{ key: 'close', label: 'Close', points: minutes.price }}
      fills={layers.fills}
      levels={layers.levels}
      segments={
        arrival === null
          ? []
          : [
              {
                key: 'arrival',
                label: 'Arrival mid',
                value: arrival,
                from: start,
                to: end,
                color: NET_COLOR,
                style: 'dotted',
                weight: 'guide',
                text: 'Arrival',
                textPosition: 'insideStartTop',
              },
            ]
      }
      volume={minutes.volume}
      valueFormat={(value) => formatLocalePrice(value, digits)}
      timeZone="local"
    />
  );
}

function AssetView({
  day,
  run,
  dayKey,
  order,
}: {
  day: ExecutionDay;
  run: BacktestRunKey;
  dayKey: string;
  order: ExecutionOrder;
}) {
  const query = useBacktestExecutionAsset(run, dayKey, order.asset);
  if (query.data) return <AssetChart day={day} order={order} data={query.data} />;
  if (query.error) {
    return <ErrorPanel message={query.error.message} onRetry={() => void query.refetch()} />;
  }
  return <LoadingSkeleton variant="chart" label={`Loading ${order.asset}`} />;
}

// --------------------------------------------------------------------------- #
// Tables
// --------------------------------------------------------------------------- #

function CostTable({ day }: { day: ExecutionDay }) {
  const horizons = Object.fromEntries(day.policies.map((p) => [p.name, p.horizon_minutes]));
  const markouts = Object.keys(day.summary[0]?.markouts_bps ?? {});
  return (
    <DataTable
      dense
      data={day.summary.map((row) => ({
        ...row,
        horizon: horizons[row.policy] ?? null,
        ...Object.fromEntries(markouts.map((h) => [`markout_${h}`, row.markouts_bps[h] ?? null])),
      }))}
      rowKey={(row) => row.policy}
      columns={[
        { key: 'policy', header: 'Policy', format: (value) => humanize(String(value)) },
        { key: 'horizon', header: 'Horizon (min)', kind: 'count' },
        { key: 'total_bps', header: 'Cost (bp)', kind: 'number', digits: 1 },
        { key: 'fee_bps', header: 'Fee', kind: 'number', digits: 1 },
        { key: 'spread_bps', header: 'Spread', kind: 'number', digits: 1 },
        { key: 'drift_bps', header: 'Drift', kind: 'number', digits: 1 },
        { key: 'unfilled_bps', header: 'Unfilled', kind: 'number', digits: 1 },
        { key: 'maker_share', header: 'Maker', kind: 'percent', digits: 0 },
        { key: 'filled_share', header: 'Filled', kind: 'percent', digits: 0 },
        { key: 'minutes_to_complete', header: 'Median min', kind: 'count' },
        ...markouts.map((h) => ({
          key: `markout_${h}`,
          header: `Markout ${h}`,
          kind: 'number' as const,
          digits: 1,
        })),
        { key: 'below_minimum', header: 'Below min', kind: 'count' },
      ]}
    />
  );
}

function OrdersTable({ day }: { day: ExecutionDay }) {
  return (
    <DataTable
      dense
      data={day.orders.map((order) => ({
        asset: order.asset,
        side: order.side > 0 ? 'Buy' : 'Sell',
        notional: order.notional,
        ...order.cost_bps,
      }))}
      rowKey={(row) => row.asset}
      maxRows={500}
      columns={[
        {
          key: 'asset',
          header: 'Asset',
          render: (value) => (
            <Link to={`?asset=${encodeURIComponent(String(value))}`}>{String(value)}</Link>
          ),
        },
        { key: 'side', header: 'Side' },
        { key: 'notional', header: 'Notional', kind: 'money', digits: 0 },
        ...day.policies.map((policy) => ({
          key: policy.name,
          header: `${humanize(policy.name)} (bp)`,
          kind: 'number' as const,
          digits: 1,
        })),
      ]}
    />
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

function DayBody({ day, run, dayKey }: { day: ExecutionDay; run: BacktestRunKey; dayKey: string }) {
  const [search] = useSearchParams();
  const selected = search.get('asset');
  const order = day.orders.find((item) => item.asset === selected) ?? day.orders[0];
  const dates = useMemo(() => day.book_times.map((value) => new Date(value)), [day]);
  const { assumptions } = day;
  return (
    <Stack gap="section">
      <TerminalSection title="Capital in transit">
        <CapitalInTransit day={day} dates={dates} />
      </TerminalSection>
      <TerminalSection title="Running cost">
        <RunningCost day={day} dates={dates} />
      </TerminalSection>
      {order ? (
        <TerminalSection
          title={`Asset · ${order.asset} · ${order.side > 0 ? 'Buy' : 'Sell'} ${money(order.notional)}`}
        >
          <AssetView key={order.asset} day={day} run={run} dayKey={dayKey} order={order} />
        </TerminalSection>
      ) : null}
      <TerminalSection title="Cost by policy">
        <CostTable day={day} />
      </TerminalSection>
      <TerminalSection title={`Orders · ${day.orders.length}`}>
        <OrdersTable day={day} />
      </TerminalSection>
      <TerminalSection title="Assumptions">
        <Text as="p" variant="caption">
          {`Each order is worked alone on ${day.venue}, from the first minute after the decision (${day.decision_at}). Capital in transit is each order's unfilled quantity at its arrival mid. Running cost adds, at each moment, what the fills so far cost against arrival (fees included) and the unfilled quantity marked at the last close against arrival, so it ends at the policy's total. Costs in the tables are in bp of the order at arrival mid; positive is worse, and drift (price moving while the order works) dominates any single day, so judge policies across many days. Bars carry no quotes: the book is an assumed ${assumptions.assumed_spread_bps ?? '—'} bp spread around the last close, a resting order fills ${formatPercent(assumptions.touch_fill_prob, 0)} of a touch, and fills take at most ${formatPercent(assumptions.participation, 0)} of a minute's volume.${
            day.skipped.length ? ` No bars for: ${day.skipped.join(', ')}.` : ''
          }`}
        </Text>
      </TerminalSection>
    </Stack>
  );
}

export function BacktestExecutionDayPage() {
  const { family = '', version = '', preset = '', runId = '', day = '' } = useParams();
  const run = { family, version, preset, runId };
  const query = useBacktestExecutionDay(run, day);
  const data = query.data;
  return (
    <TerminalPage
      title={`${preset} · rebalance ${day}`}
      subtitle={`${family} / ${version} / ${runId}`}
      right={
        <Cluster gap="stack">
          {data ? <Badge variant="ghost">{`${data.orders.length} orders`}</Badge> : null}
          <Link
            to={runHref({ family, version, preset, run_id: runId })}
            variant="control"
            size="sm"
          >
            Run replay
          </Link>
        </Cluster>
      }
    >
      {data ? (
        <DayBody day={data} run={run} dayKey={day} />
      ) : isLoadingData(query) ? (
        <Stack gap="section">
          <LoadingSkeleton variant="chart" label="Simulating the rebalance day" />
          <LoadingSkeleton variant="chart" announce={false} />
          <LoadingSkeleton variant="table" count={4} announce={false} />
        </Stack>
      ) : (
        <ErrorPanel
          message={query.error?.message ?? `No rebalance on ${day}.`}
          onRetry={() => void query.refetch()}
        />
      )}
    </TerminalPage>
  );
}
