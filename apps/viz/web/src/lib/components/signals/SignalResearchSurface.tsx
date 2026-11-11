/**
 * Signal research surface: cumulative IC per arm, metrics, quantile returns, and gates for the
 * run a signal version selected with `signals.research_surface.publish_research_surface`. An arm
 * without an IC series or quantile table is left out of that chart or table; a not_tested surface
 * shows its blocker, gates, and record with no arm views.
 *
 * USAGE:
 *   <SignalResearchSurface family="example" memoryVersion="v002" />
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
import { useQueries } from '@tanstack/react-query';
import { useState } from 'react';
import {
  getSignalSurfaceIc,
  getSignalSurfaceQuantiles,
  type SignalSurfaceArm,
  signalKeys,
  useSignalResearchSurface,
} from '@/lib/api/signals';
import { STALE } from '@/lib/api/stale-times';
import {
  Badge,
  ErrorPanel,
  isLoadingData,
  LoadingSkeleton,
  QueryState,
  SegmentedControl,
  TerminalSection,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Control first, so it reads as the reference column and the first chart line. */
function orderedArms(arms: readonly SignalSurfaceArm[]): SignalSurfaceArm[] {
  return [...arms].sort((a, b) => Number(b.role === 'control') - Number(a.role === 'control'));
}

function armColor(arm: SignalSurfaceArm, index: number): string {
  return arm.role === 'control' ? chartColor('baseline') : chartPaletteColor(index);
}

/** Compare the first candidate against the control when both are among the given arms. */
function controlDifference(arms: readonly SignalSurfaceArm[]) {
  const control = arms.find((arm) => arm.role === 'control');
  const candidate = arms.find((arm) => arm.role === 'candidate');
  return control && candidate
    ? { current: candidate.arm_id, reference: control.arm_id }
    : undefined;
}

function formatGateNumber(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toPrecision(4) : '—';
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface SignalResearchSurfaceProps {
  family: string;
  memoryVersion: string;
}

export function SignalResearchSurface({ family, memoryVersion }: SignalResearchSurfaceProps) {
  const surfaceQuery = useSignalResearchSurface(family, memoryVersion);
  const arms = orderedArms(surfaceQuery.data?.arms ?? []);
  const icQueries = useQueries({
    queries: arms.map((arm) => ({
      queryKey: signalKeys.surfaceTable(family, memoryVersion, arm.arm_id, 'ic'),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getSignalSurfaceIc(family, memoryVersion, arm.arm_id, signal),
      staleTime: STALE.analysis,
      enabled: arm.ic !== null,
    })),
  });
  const quantileQueries = useQueries({
    queries: arms.map((arm) => ({
      queryKey: signalKeys.surfaceTable(family, memoryVersion, arm.arm_id, 'quantiles'),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getSignalSurfaceQuantiles(family, memoryVersion, arm.arm_id, signal),
      staleTime: STALE.analysis,
      enabled: arm.quantiles !== null,
    })),
  });
  const primaryTarget = surfaceQuery.data?.primary_target;
  const targets = [
    ...new Set([
      ...(primaryTarget ? [primaryTarget] : []),
      ...arms.flatMap((arm) => arm.targets),
      ...quantileQueries.flatMap((query) => (query.data ?? []).map((row) => row.target_id)),
    ]),
  ];
  const [requestedTarget, setTarget] = useState<string | null>(null);
  const target =
    requestedTarget && targets.includes(requestedTarget) ? requestedTarget : targets[0];

  const surface = surfaceQuery.data;
  if (!surface) {
    return (
      <QueryState
        query={surfaceQuery}
        skeleton="chart"
        isEmpty
        emptyTitle="No research surface"
        emptyHint="This version has not published a signal research surface."
      >
        {null}
      </QueryState>
    );
  }

  const columns: MetricComparisonColumn[] = arms.map((arm, index) => ({
    id: arm.arm_id,
    label: arm.label,
    detail: arm.role === 'control' ? 'Control' : 'Candidate',
    description: arm.description || undefined,
    color: armColor(arm, index),
  }));
  const difference = controlDifference(arms);
  const metricKeys = [...new Set(arms.flatMap((arm) => Object.keys(arm.metrics.values)))];
  const metricRows: MetricComparisonRow[] = metricKeys.map((key) => ({
    key,
    label: key,
    format: 'number',
    values: Object.fromEntries(arms.map((arm) => [arm.arm_id, arm.metrics.values[key]])),
  }));

  const icLoading = icQueries.some(isLoadingData);
  const icError = icQueries.find((query) => query.error && !query.data)?.error ?? null;
  const icSeries = arms.flatMap((arm, index) =>
    arm.ic === null
      ? []
      : [
          {
            metric: arm.arm_id,
            axis: 'left' as const,
            label: arm.label,
            points: (icQueries[index]?.data ?? [])
              .filter((row) => row.target_id === target)
              .map((row) => ({ x: row.decision_time, y: row.cumulative_ic })),
          },
        ],
  );
  const hasIc = icSeries.some((series) => series.points.length > 0);
  const armsWithoutIc = arms.filter((arm) => arm.ic === null);
  const metricColors = Object.fromEntries(
    arms.map((arm, index) => [arm.arm_id, armColor(arm, index)]),
  );

  const quantileArms = arms.filter((arm) => arm.quantiles !== null);
  const quantileColumns = columns.filter((column) =>
    quantileArms.some((arm) => arm.arm_id === column.id),
  );
  const quantileLoading = quantileQueries.some(isLoadingData);
  const quantileError = quantileQueries.find((query) => query.error && !query.data)?.error ?? null;
  const buckets = new Map<number, string>();
  for (const query of quantileQueries) {
    for (const row of query.data ?? []) {
      if (row.target_id === target) buckets.set(row.quantile, row.label);
    }
  }
  const quantileRows: MetricComparisonRow[] = [...buckets.entries()]
    .sort(([a], [b]) => a - b)
    .map(([quantile, label]) => ({
      key: String(quantile),
      label,
      format: 'number',
      values: Object.fromEntries(
        arms.flatMap((arm, index) =>
          arm.quantiles === null
            ? []
            : [
                [
                  arm.arm_id,
                  quantileQueries[index]?.data?.find(
                    (row) => row.target_id === target && row.quantile === quantile,
                  )?.mean_target,
                ],
              ],
        ),
      ),
    }));

  const gateRows = surface.gates.map((gate) => ({
    Gate: gate.name,
    Stage: gate.stage ?? '—',
    Statistic: gate.statistic ?? '—',
    Value: formatGateNumber(gate.value),
    Requirement: `${gate.comparison ?? ''} ${formatGateNumber(gate.threshold)}`.trim(),
    Status: gate.passed ? 'Pass' : 'Fail',
  }));

  const gatesSection =
    gateRows.length > 0 ? (
      <TerminalSection title="Gates">
        <DataTable data={gateRows} maxRows={gateRows.length} />
      </TerminalSection>
    ) : null;
  const recordSection = (
    <TerminalSection title="Record" right={`${surface.state} · ${surface.run_id}`}>
      <Text as="p" size="sm">
        {surface.summary}
      </Text>
      {surface.disclosures.map((text) => (
        <Text key={text} as="p" tone="muted" size="sm">
          {text}
        </Text>
      ))}
      <Text as="p" tone="muted" size="xs">
        {[
          `${surface.experiment} · published ${surface.published_at.slice(0, 10)}`,
          ...surface.provenance.map((item) => `${item.label}: ${item.value}`),
        ].join(' · ')}
      </Text>
    </TerminalSection>
  );

  if (surface.state === 'not_tested') {
    return (
      <>
        <TerminalSection
          title={surface.title}
          right={
            <Badge tone="warning" size="sm">
              not tested
            </Badge>
          }
        >
          <Text as="p" size="sm">
            {surface.blocker}
          </Text>
        </TerminalSection>
        {gatesSection}
        {recordSection}
      </>
    );
  }

  return (
    <>
      <TerminalSection
        title={surface.title}
        right={
          targets.length > 1 ? (
            <SegmentedControl
              size="xs"
              ariaLabel="Evaluation target"
              options={targets.map((value) => ({ value, label: value }))}
              value={target ?? ''}
              onValueChange={setTarget}
            />
          ) : (
            target
          )
        }
      >
        {icLoading ? (
          <LoadingSkeleton variant="chart" />
        ) : icError ? (
          <ErrorPanel
            message={icError.message}
            onRetry={() => {
              for (const query of icQueries) if (query.error) void query.refetch();
            }}
          />
        ) : hasIc ? (
          <MultiSeriesTimeChart
            title={`Cumulative IC · ${target}`}
            series={icSeries}
            metricColors={metricColors}
            valueFormat="number"
          />
        ) : icSeries.length > 0 ? (
          <Text as="p" tone="muted" size="sm">
            {`No IC series for target ${target}.`}
          </Text>
        ) : null}
        {armsWithoutIc.map((arm) => (
          <Text key={arm.arm_id} as="p" tone="muted" size="sm">
            {`${arm.label}: no IC series in this run.`}
          </Text>
        ))}
      </TerminalSection>

      <TerminalSection title="Metrics">
        <MetricComparisonTable columns={columns} rows={metricRows} difference={difference} />
      </TerminalSection>

      {quantileArms.length > 0 ? (
        <TerminalSection title={`Quantile returns · ${target}`}>
          {quantileLoading ? (
            <LoadingSkeleton variant="table" />
          ) : quantileError ? (
            <ErrorPanel
              message={quantileError.message}
              onRetry={() => {
                for (const query of quantileQueries) if (query.error) void query.refetch();
              }}
            />
          ) : quantileRows.length > 0 ? (
            <MetricComparisonTable
              columns={quantileColumns}
              rows={quantileRows}
              difference={controlDifference(quantileArms)}
            />
          ) : (
            <Text as="p" tone="muted" size="sm">
              {`No quantile returns for target ${target}.`}
            </Text>
          )}
        </TerminalSection>
      ) : null}

      {gatesSection}
      {recordSection}
    </>
  );
}
