/**
 * Backtest Engine live dashboard: run counts, every saved strategy run newest first (running
 * rows pinned), each row opening its replay, and the Update-backtest jobs.
 *
 * USAGE:
 *   Routed at /backtest-engine; a run row opens /backtest-engine/runs/:family/:version/:preset/:runId.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  DataTable,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowLink,
} from '@quant-factory/qf-ui/tables';
import { useState } from 'react';
import {
  type BacktestRun,
  type BacktestRunList,
  type BacktestRunState,
  runHref,
  useBacktestEngineRuns,
} from '@/lib/api/backtestEngine';
import {
  Badge,
  Button,
  Cluster,
  EmptyState,
  ErrorPanel,
  FacetedFilter,
  formatDuration,
  formatNumber,
  formatPercent,
  formatShortDateTime,
  humanize,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  RelativeTime,
  ScrollArea,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  StatusDot,
  Surface,
  TerminalPage,
  TerminalSection,
} from '@/ui';
import { RunStateBadge } from './runs';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const STATES: readonly BacktestRunState[] = ['running', 'succeeded', 'failed'];

/** Live elapsed time for a running run, recorded duration otherwise. */
function duration(run: BacktestRun, now: number): string {
  if (run.state === 'running' && run.started_at) {
    return formatDuration(Math.max(0, (now - Date.parse(run.started_at)) / 1000));
  }
  return formatDuration(run.duration_s);
}

// --------------------------------------------------------------------------- #
// Header strip
// --------------------------------------------------------------------------- #

function HeaderStrip({ data, now }: { data: BacktestRunList; now: number }) {
  const { summary } = data;
  return (
    <StatGrid variant="strip" boxed aria-label="Backtest run summary">
      <StatItem
        label="Running"
        value={
          <Cluster gap="stack" wrap={false}>
            {summary.running ? <StatusDot tone="running" /> : null}
            <span>{summary.running}</span>
          </Cluster>
        }
      />
      <StatItem
        label="Failed · 24h"
        value={summary.failed_24h}
        tone={summary.failed_24h ? 'critical' : 'default'}
      />
      <StatItem label="Runs · 7d" value={summary.runs_7d} />
      <StatItem
        label="Last finished"
        value={<RelativeTime value={summary.last_finished_at} now={now} />}
      />
    </StatGrid>
  );
}

// --------------------------------------------------------------------------- #
// Runs table
// --------------------------------------------------------------------------- #

/** The preset without its version prefix (`v002__base` → `base`); the version shows beside it. */
function presetLabel(run: BacktestRun): string {
  const prefix = `${run.version}__`;
  return run.preset.startsWith(prefix) ? run.preset.slice(prefix.length) : run.preset;
}

function RunsTable({ runs, now }: { runs: BacktestRun[]; now: number }) {
  const ordered = [
    ...runs.filter((run) => run.state === 'running'),
    ...runs.filter((run) => run.state !== 'running'),
  ];
  return (
    <Surface padding="none" clip className="flex min-h-0 flex-col">
      <ScrollArea axis="both" label="Backtest runs" className="min-h-0">
        <Table density="dense" aria-label="Backtest runs">
          <TableHeader sticky>
            <TableRow>
              <TableHead scope="col">Status</TableHead>
              <TableHead scope="col">Run</TableHead>
              <TableHead scope="col" numeric>
                Sharpe
              </TableHead>
              <TableHead scope="col" numeric>
                Total return
              </TableHead>
              <TableHead scope="col" numeric>
                Max DD
              </TableHead>
              <TableHead scope="col" numeric>
                Started
              </TableHead>
              <TableHead scope="col" numeric>
                Duration
              </TableHead>
              <TableHead scope="col">Engine</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordered.map((run) => (
              <TableRow key={runHref(run)}>
                <TableCell>
                  <RunStateBadge state={run.state} />
                </TableCell>
                <TableCell detail={run.error ?? `${run.family} · ${run.version}`}>
                  <TableRowLink to={runHref(run)} title={run.run_id}>
                    {presetLabel(run)}
                  </TableRowLink>
                </TableCell>
                <TableCell numeric>{formatNumber(run.metrics.sharpe, 2)}</TableCell>
                <TableCell numeric>{formatPercent(run.metrics.total_return)}</TableCell>
                <TableCell numeric>{formatPercent(run.metrics.max_drawdown)}</TableCell>
                <TableCell numeric>
                  {run.started_at ? (
                    <RelativeTime value={run.started_at} now={now} />
                  ) : (
                    formatShortDateTime(run.finished_at)
                  )}
                </TableCell>
                <TableCell numeric>{duration(run, now)}</TableCell>
                <TableCell>
                  {run.engine ? (
                    <Badge size="sm" variant="ghost">
                      {run.engine}
                    </Badge>
                  ) : (
                    '—'
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ScrollArea>
    </Surface>
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

export function BacktestEnginePage() {
  const [families, setFamilies] = useState<string[]>([]);
  const [states, setStates] = useState<BacktestRunState[]>([]);
  const query = useBacktestEngineRuns({ families, states });
  const data = query.data;
  // Elapsed and relative times advance with each poll (every 5s while anything runs).
  const now = query.dataUpdatedAt;
  const filtering = families.length + states.length > 0;
  const clear = () => {
    setFamilies([]);
    setStates([]);
  };
  // Finished update jobs are history; only running or failed ones need attention here.
  const updates = (data?.updates ?? []).filter((job) => job.state !== 'done');

  // Polling keeps the page current, so it shows connection state only when it is lost.
  return (
    <TerminalPage title="Backtest Engine" fill>
      <Inset padding="pane" className="flex min-h-0 flex-1 flex-col">
        <Stack gap="section" className="min-h-0 flex-1">
          {isLoadingData(query) ? (
            <LoadingSkeleton variant="card" count={4} label="Loading run summary" />
          ) : data ? (
            <Stack gap="stack">
              {query.isError ? (
                <StateMessage state="error">
                  Disconnected · showing the last data received.
                </StateMessage>
              ) : null}
              <HeaderStrip data={data} now={now} />
            </Stack>
          ) : (
            <ErrorPanel
              message="Unable to load backtest runs."
              onRetry={() => void query.refetch()}
            />
          )}
          {updates.length ? (
            <TerminalSection title="Update-backtest jobs">
              <DataTable
                data={updates}
                rowKey={(job) => `${job.family}/${job.version}`}
                columns={[
                  {
                    key: 'state',
                    header: 'Status',
                    render: (value) => <RunStateBadge state={String(value)} />,
                  },
                  { key: 'family', header: 'Family' },
                  { key: 'version', header: 'Version' },
                  {
                    key: 'started_at',
                    header: 'Started',
                    format: (value) => formatShortDateTime(value as string | null),
                  },
                  {
                    key: 'finished_at',
                    header: 'Finished',
                    format: (value) => formatShortDateTime(value as string | null),
                  },
                  {
                    key: 'error',
                    header: 'Error',
                    truncate: 'end',
                    format: (value) => (value as string | null) ?? '—',
                  },
                ]}
                emptyTitle="No update jobs"
                emptyHint="Strategies → Backtesting → Update backtest starts one."
              />
            </TerminalSection>
          ) : null}
          <TerminalSection title="Runs" fill>
            <Stack gap="stack" className="min-h-0 flex-1">
              <Cluster gap="stack">
                <FacetedFilter
                  title="Family"
                  options={(data?.families ?? families).map((value) => ({ value, label: value }))}
                  selected={families}
                  onSelectedChange={setFamilies}
                />
                <FacetedFilter
                  title="Status"
                  options={STATES.map((value) => ({ value, label: humanize(value) }))}
                  selected={states}
                  onSelectedChange={setStates}
                />
                {filtering ? (
                  <Button variant="control" size="sm" onClick={clear}>
                    Clear filters
                  </Button>
                ) : null}
              </Cluster>
              {isLoadingData(query) ? (
                <LoadingSkeleton variant="table" count={6} label="Loading backtest runs" />
              ) : !data ? null : data.runs.length === 0 ? (
                <EmptyState
                  title={filtering ? 'No runs match these filters.' : 'No backtest runs saved yet.'}
                  hint={
                    filtering ? undefined : 'Runs appear here as soon as a strategy run starts.'
                  }
                />
              ) : (
                <RunsTable runs={data.runs} now={now} />
              )}
            </Stack>
          </TerminalSection>
        </Stack>
      </Inset>
    </TerminalPage>
  );
}
