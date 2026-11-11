/**
 * Chart-first presentation of the selected account's saved portfolio diagnostics.
 * USAGE: <PortfolioDiagnostics strategyType={family} memoryVersion={version} runId={run} account={account} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  ChartToggleGroup,
  displaySeries,
  MultiSeriesTimeChart,
  type MultiSeriesTimeChartProps,
} from '@quant-factory/qf-ui/charts';
import { useState } from 'react';
import { usePortfolioDiagnostics } from '@/lib/api/portfolio-diagnostics';
import {
  EmptyState,
  ErrorPanel,
  isLoadingData,
  LoadingSkeleton,
  Stack,
  TerminalSection,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PortfolioDiagnostics({
  strategyType,
  memoryVersion,
  runId,
  account,
}: {
  strategyType: string;
  memoryVersion: string;
  runId: string | null;
  account: string | null;
}) {
  const { metadata, evidence } = usePortfolioDiagnostics(
    strategyType,
    memoryVersion,
    runId,
    account,
  );
  const [scenario, setScenario] = useState('observed');
  const [requirement, setRequirement] = useState('maintenance:0.01');
  const [units, setUnits] = useState('percent');
  const [window, setWindow] = useState('30');
  const report = metadata.data?.report;
  if (!runId)
    return (
      <EmptyState
        title="Portfolio diagnostics unavailable"
        hint="This version has no selected research run."
      />
    );
  if (isLoadingData(metadata)) return <LoadingSkeleton variant="chart" />;
  if (metadata.error && !metadata.data)
    return (
      <ErrorPanel
        message={metadata.error.message}
        onRetry={() => {
          void metadata.refetch();
        }}
      />
    );
  if (!report)
    return (
      <EmptyState
        title="Portfolio diagnostics unavailable"
        hint="No completed report is explicitly selected for this version, research run and account."
      />
    );
  if (isLoadingData(evidence)) return <LoadingSkeleton variant="chart" />;
  if (evidence.error && !evidence.data)
    return (
      <ErrorPanel
        message={evidence.error.message}
        onRetry={() => {
          void evidence.refetch();
        }}
      />
    );
  const data = evidence.data;
  if (!data) return <EmptyState title="Report evidence unavailable" />;
  const { summary, selection } = report;
  const initialCapital = summary.conventions.initial_equity;
  const [basis, rateText] = requirement.split(':');
  const rate = Number(rateText);
  const peak = summary.capital.headline.find(
    (item) => item.scenario === scenario && item.basis === basis && item.rate === rate,
  );
  const capital = data.capital.filter(
    (row) => row.scenario === scenario && row.basis === basis && row.rate === rate,
  );
  const close = data.exposure.filter((row) => row.point === 'day_close');
  const fill = data.exposure.filter((row) => row.point === 'post_fill');
  const rolling = data.rolling.filter((row) => row.window === Number(window));
  const series = (
    label: string,
    rows: readonly { timestamp: string }[],
    values: readonly (number | null)[],
    scale = 1,
    cumulative = false,
  ): MultiSeriesTimeChartProps['series'][number] => ({
    metric: label,
    label,
    axis: 'left',
    points: displaySeries(
      rows.map((row, index) => ({ x: row.timestamp, y: values[index] ?? null })),
      { scale, cumulative },
    ),
  });
  const zero = series(
    'Zero reference',
    close,
    close.map(() => 0),
  );
  const money = units === 'dollars';
  const availableRequirements = (forScenario: string) =>
    requirements.filter((option) =>
      summary.capital.headline.some(
        (item) => `${item.basis}:${item.rate}` === option.value && item.scenario === forScenario,
      ),
    );
  const requirements = [
    { value: 'maintenance:0.01', label: 'Maintenance 1%' },
    { value: 'maintenance:0.025', label: 'Maintenance 2.5%' },
    { value: 'maintenance:0.05', label: 'Maintenance 5%' },
    { value: 'initial:0.05', label: 'Assumed initial 5%' },
    { value: 'initial:0.1', label: 'Assumed initial 10%' },
    { value: 'initial:0.2', label: 'Assumed initial 20%' },
  ];
  return (
    <Stack gap="block">
      <TerminalSection
        title="Capital"
        right={`${selection.memory_version} · ${selection.source_account} · ${selection.source_run_id} · ${summary.status} · C0 $${initialCapital.toLocaleString()}`}
      >
        <Stack gap="heading">
          <MultiSeriesTimeChart
            title="Daily maximum reserve and total backing"
            downsample={false}
            valueFormat={money ? 'money' : 'percent-delta'}
            axisLabels={{ left: money ? 'USD' : '% of C0' }}
            headerRight={
              <>
                <ChartToggleGroup
                  ariaLabel="Capital scenario"
                  value={scenario}
                  options={[
                    { value: 'observed', label: 'Observed', title: 'Observed hourly path' },
                    {
                      value: 'daily_wick_stress',
                      label: 'Wick stress',
                      title: 'Hypothetical daily-wick stress',
                    },
                  ]}
                  onChange={(value) => {
                    setScenario(value);
                    const offered = availableRequirements(value);
                    if (!offered.some((option) => option.value === requirement))
                      setRequirement(offered[0]?.value ?? 'maintenance:0.01');
                  }}
                />
                <ChartToggleGroup
                  variant="menu"
                  label="Margin"
                  ariaLabel="Capital requirement"
                  value={requirement}
                  options={availableRequirements(scenario)}
                  onChange={setRequirement}
                />
                <ChartToggleGroup
                  ariaLabel="Capital units"
                  value={units}
                  options={[
                    { value: 'percent', label: '%', ariaLabel: '% of starting capital' },
                    { value: 'dollars', label: '$', ariaLabel: 'Actual-run dollars' },
                  ]}
                  onChange={setUnits}
                />
              </>
            }
            series={
              capital.length
                ? [
                    series(
                      'Extra reserve',
                      capital,
                      capital.map((row) => row.reserve_needed),
                      money ? 1 : 1 / initialCapital,
                    ),
                    series(
                      'Total backing',
                      capital,
                      capital.map((row) => row.backing_multiple),
                      money ? initialCapital : 1,
                    ),
                  ]
                : []
            }
          />
          <Text as="p" size="sm" tone="muted">
            Peak extra reserve:{' '}
            {peak
              ? `$${peak.peak_reserve.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${((100 * peak.peak_reserve) / initialCapital).toFixed(2)}% of C0) · total backing $${peak.capital_to_supply.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · ${peak.peak_at ? `${new Date(peak.peak_at).toISOString().slice(0, 10)} UTC` : 'No reserve needed'}`
              : 'Unavailable'}
            . Daily maxima preserve intraday stress. Total backing of 120% means 20% extra reserve.
          </Text>
        </Stack>
      </TerminalSection>
      <MultiSeriesTimeChart
        title="Neutrality · holdings × dated BTC model betas"
        valueFormat="percent-delta"
        axisLabels={{ left: '% of NAV' }}
        series={[
          series(
            'After fill',
            fill,
            fill.map((row) => row.btc_exposure),
          ),
          series(
            'Day close',
            close,
            close.map((row) => row.btc_exposure),
          ),
          series(
            'Drift since fill',
            close,
            close.map((row) => row.drift_since_fill),
          ),
          zero,
        ]}
      />
      <TerminalSection title="Realized BTC beta">
        <Stack gap="heading">
          <MultiSeriesTimeChart
            title="Return regression · saved 95% confidence bounds"
            headerRight={
              <ChartToggleGroup
                ariaLabel="Realized beta window"
                value={window}
                options={[
                  { value: '30', label: '30D', ariaLabel: '30 days' },
                  { value: '90', label: '90D', ariaLabel: '90 days' },
                ]}
                onChange={setWindow}
              />
            }
            series={[
              series(
                'Realized beta',
                rolling,
                rolling.map((row) => row.beta),
              ),
              series(
                '95% lower bound',
                rolling,
                rolling.map((row) => row.beta_ci95_low),
              ),
              series(
                '95% upper bound',
                rolling,
                rolling.map((row) => row.beta_ci95_high),
              ),
              zero,
            ]}
          />
        </Stack>
      </TerminalSection>
      <MultiSeriesTimeChart
        title="Cumulative P&L attribution"
        valueFormat="money"
        axisLabels={{ left: 'USD · actual run' }}
        series={[
          series(
            'BTC-factor P&L',
            data.attribution,
            data.attribution.map((row) => row.btc_factor_pnl),
            1,
            true,
          ),
          series(
            'Residual price P&L',
            data.attribution,
            data.attribution.map((row) => row.residual_price_pnl),
            1,
            true,
          ),
          series(
            'Unmodeled price P&L',
            data.attribution,
            data.attribution.map((row) => row.unmodeled_price_pnl),
            1,
            true,
          ),
          series(
            'Signed funding',
            data.attribution,
            data.attribution.map((row) => row.funding),
            1,
            true,
          ),
          series(
            'Negative fees',
            data.attribution,
            data.attribution.map((row) => row.fees),
            -1,
            true,
          ),
          series(
            'Net P&L',
            data.attribution,
            data.attribution.map((row) => row.net_pnl),
            1,
            true,
          ),
        ]}
      />
      <MultiSeriesTimeChart
        title="Positioning · day close"
        valueFormat="percent-delta"
        axisLabels={{ left: '% of NAV' }}
        series={[
          series(
            'Long exposure',
            close,
            close.map((row) => row.long_exposure),
          ),
          series(
            'Short magnitude',
            close,
            close.map((row) => row.short_exposure),
          ),
          series(
            'Gross exposure',
            close,
            close.map((row) => row.gross_leverage),
          ),
          series(
            'Net exposure',
            close,
            close.map((row) => row.net_exposure),
          ),
        ]}
      />
      <MultiSeriesTimeChart
        title="Risk · daily volatility"
        valueFormat="percent-delta"
        series={[
          series(
            'Saved predicted daily volatility',
            close,
            close.map((row) => row.predicted_total_vol),
          ),
          series(
            'Full-window realized daily price volatility (constant)',
            close,
            close.map(() => summary.risk.realized_price_vol),
          ),
        ]}
      />
      <TerminalSection title="Report provenance and interpretation" right={selection.attempt_id}>
        <Stack gap="stack">
          <Text as="p" size="sm">
            Account: {selection.source_account} · Source run: {selection.source_run_id}
          </Text>
          <Text as="p" size="sm">
            Range: {data.attribution[0]?.timestamp.slice(0, 10)} –{' '}
            {data.attribution.at(-1)?.timestamp.slice(0, 10)} · {summary.coverage.days} days ·
            predicted risk {summary.coverage.days_with_predicted_risk} days · missing snapshots{' '}
            {summary.coverage.points_without_snapshot}
          </Text>
          {[
            ...summary.labels,
            summary.conventions.retained_profit,
            summary.conventions.scaling,
            'Cumulative P&L uses the complete saved history before zooming. Missing observations remain gaps; a missing P&L observation makes subsequent cumulative totals unavailable. Statistical windows retain their saved warmup.',
          ].map((label) => (
            <Text key={label} as="p" size="sm" tone="muted">
              {label}
            </Text>
          ))}
        </Stack>
      </TerminalSection>
    </Stack>
  );
}
