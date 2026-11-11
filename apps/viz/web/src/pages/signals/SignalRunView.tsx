/**
 * Persisted signal run view — metrics, chart, metadata, config, stats, preview.
 *
 * Renders one run of a signal id under db/signals. The version page mounts it for canonical
 * (registered engine) versions, so a persisted run has no route of its own.
 *
 * USAGE:
 *   <SignalRunView signalId="example-default" runId="run-..." showChart />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { Suspense } from 'react';
import { signalRunPanel } from '@/extensions';
import { useSignalData, useSignalStats } from '@/lib/api/signals';
import { SignalChart } from '@/lib/components/charts/SignalChart';
import {
  Badge,
  Cluster,
  CodeBlock,
  Disclosure,
  formatCount,
  formatNumber,
  Grid,
  LoadingSkeleton,
  QueryState,
  Stack,
  Stat,
  TerminalSection,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function formatValue(value: unknown): string {
  if (value == null) return '-';
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface SignalRunViewProps {
  signalId: string;
  runId: string;
  /** False when the page already renders a family chart above this view. */
  showChart: boolean;
}

export function SignalRunView({ signalId, runId, showChart }: SignalRunViewProps) {
  const dataQuery = useSignalData(signalId, runId);
  const statsQuery = useSignalStats(signalId, runId);
  const signalData = dataQuery.data ?? null;
  const stats = statsQuery.data ?? null;

  const chartData = (() => {
    if (!signalData?.data || !signalData.prediction_columns?.length) return [];
    const dateCol = signalData.date_column || 'timestamp';
    const predCol = signalData.prediction_columns[0];
    if (!predCol) return [];
    const points: Array<{ date: Date; value: number }> = [];
    for (const row of signalData.data) {
      if (row[dateCol] == null || row[predCol] == null) continue;
      points.push({
        date: new Date(row[dateCol] as string),
        value: row[predCol] as number,
      });
    }
    return points.sort((a, b) => a.date.getTime() - b.date.getTime());
  })();

  const specializedPanel = signalData
    ? signalRunPanel(String(signalData.config.signal_type ?? ''))
    : undefined;
  const SpecializedPanel = specializedPanel?.component;

  return (
    <QueryState
      query={dataQuery}
      skeleton={showChart ? 'chart' : 'card'}
      onRetry={() => {
        void dataQuery.refetch();
        void statsQuery.refetch();
      }}
    >
      {signalData ? (
        <Stack gap="block">
          {Object.keys(signalData.metrics).length > 0 ? (
            <TerminalSection title="metrics">
              <Grid minItemWidth="sm">
                {Object.entries(signalData.metrics).map(([key, value]) => (
                  <Stat key={key} mono label={key} value={formatValue(value)} />
                ))}
              </Grid>
            </TerminalSection>
          ) : null}

          {showChart && SpecializedPanel ? (
            <Suspense fallback={<LoadingSkeleton variant="chart" />}>
              <SpecializedPanel
                signalData={signalData}
                chartData={chartData}
                label={signalData.prediction_columns[0] || 'Prediction'}
              />
            </Suspense>
          ) : showChart && chartData.length > 0 ? (
            <SignalChart
              data={chartData}
              label={signalData.prediction_columns[0] || 'Prediction'}
            />
          ) : null}

          {signalData.metadata ? (
            <TerminalSection title="training metadata">
              <Stack>
                <Grid minItemWidth="md">
                  <Stat size="sm" mono label="Model Type" value={signalData.metadata.model_type} />
                  <Stat size="sm" mono label="Target" value={signalData.metadata.target} />
                  <Stat
                    size="sm"
                    mono
                    label="Samples"
                    value={formatCount(signalData.metadata.n_samples)}
                  />
                  <Stat size="sm" mono label="Features" value={signalData.metadata.n_features} />
                  <Stat
                    size="sm"
                    mono
                    label="Data Range"
                    value={`${signalData.metadata.data_start} → ${signalData.metadata.data_end}`}
                  />
                </Grid>
                {signalData.metadata.feature_list?.length ? (
                  <Stack gap="stack">
                    <Text as="h3" weight="semibold">
                      Top Features
                    </Text>
                    <Cluster gap="stack">
                      {signalData.metadata.feature_list.slice(0, 10).map((feature) => (
                        <Badge key={feature}>{feature}</Badge>
                      ))}
                      {signalData.metadata.feature_list.length > 10 ? (
                        <Badge variant="ghost">
                          +{signalData.metadata.feature_list.length - 10} more
                        </Badge>
                      ) : null}
                    </Cluster>
                  </Stack>
                ) : null}
              </Stack>
            </TerminalSection>
          ) : null}

          {signalData.config && Object.keys(signalData.config).length > 0 ? (
            <TerminalSection title="configuration">
              <Disclosure summary="config.json">
                <CodeBlock value={JSON.stringify(signalData.config, null, 2)} />
              </Disclosure>
            </TerminalSection>
          ) : null}

          {stats && stats.prediction_stats.length > 0 ? (
            <TerminalSection title="prediction statistics">
              <DataTable
                data={stats.prediction_stats.map((s) => ({
                  column: s.column,
                  count: s.count,
                  mean: formatNumber(s.mean, 4),
                  std: formatNumber(s.std, 4),
                  min: formatNumber(s.min, 4),
                  max: formatNumber(s.max, 4),
                }))}
                columns={['column', 'count', 'mean', 'std', 'min', 'max']}
              />
            </TerminalSection>
          ) : null}

          {signalData.data && signalData.data.length > 0 ? (
            <TerminalSection
              title="predictions preview"
              right={`first 100 of ${signalData.data.length} rows`}
            >
              <DataTable
                data={signalData.data.slice(0, 100).map((row) => {
                  const formatted: Record<string, unknown> = {};
                  for (const [key, value] of Object.entries(row)) {
                    formatted[key] = formatValue(value);
                  }
                  return formatted;
                })}
                columns={signalData.columns}
                maxRows={100}
              />
            </TerminalSection>
          ) : null}
        </Stack>
      ) : null}
    </QueryState>
  );
}
