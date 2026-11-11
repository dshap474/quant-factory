/**
 * Live read-only execution monitor: a header strip of counts and spend, one roster row
 * per agent with its 14-day trend, and the one runs table with running rows pinned first.
 *
 * USAGE: <AgentsLiveDashboard /> inside the Agents index route.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { MiniStackedBars } from '@quant-factory/qf-ui/charts/renderers';
import { chartStatusColor } from '@quant-factory/qf-ui/charts/theme';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
import {
  type AgentRunStats,
  type AgentRuns,
  useAgentRunStats,
  useAgentRuns,
} from '@/lib/api/agent-runs';
import { useAgents } from '@/lib/api/agents';
import {
  Button,
  Cluster,
  formatDuration,
  isLoadingData,
  Link,
  LoadingSkeleton,
  liveStatusTone,
  RelativeTime,
  ScrollArea,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  StatusBadge,
  StatusDot,
  type StatusTone,
  Surface,
  TerminalSection,
  Text,
  useNow,
} from '@/ui';
import { RunsTable } from './RunsTable';
import { formatCost, isRunning, runState, stateLabel } from './runs';

// --------------------------------------------------------------------------- #
// Shared hooks
// --------------------------------------------------------------------------- #

/** Default models per agent, from config bindings. */
export function useDefaultModels(): Map<string, Set<string>> {
  const agents = useAgents().data?.agents ?? [];
  return new Map(
    agents.map((agent) => [
      agent.id,
      new Set(agent.bindings.flatMap((item) => (item.model ? [item.model] : []))),
    ]),
  );
}

// --------------------------------------------------------------------------- #
// Header strip
// --------------------------------------------------------------------------- #

function HeaderStrip({
  runs,
  stats,
  now,
}: {
  runs: AgentRuns;
  stats: AgentRunStats | undefined;
  now: number;
}) {
  const summary = stats?.window;
  const complete = summary?.cost_complete_7d ?? true;
  return (
    <StatGrid variant="strip" boxed aria-label="Run summary">
      <StatItem
        label="Running"
        value={
          <Cluster gap="stack" wrap={false}>
            {runs.active_count ? <StatusDot tone="running" /> : null}
            <span>{runs.active_count}</span>
          </Cluster>
        }
      />
      <StatItem
        label="Failed · 24h"
        value={summary ? summary.failed_24h : '—'}
        tone={summary?.failed_24h ? 'critical' : 'default'}
        delta={summary ? `of ${summary.runs_24h}` : undefined}
        deltaTone="muted"
      />
      <StatItem
        label="Spend · 24h"
        value={summary ? formatCost(summary.cost_24h ?? 0, complete) : '—'}
      />
      <StatItem
        label="Spend · 7d"
        value={summary ? formatCost(summary.cost_7d ?? 0, complete) : '—'}
      />
      <StatItem
        label="Last finished"
        value={<RelativeTime value={summary?.last_finished_at} now={now} />}
      />
    </StatGrid>
  );
}

// --------------------------------------------------------------------------- #
// Roster
// --------------------------------------------------------------------------- #

export function rosterState(
  agent: AgentRuns['coverage'][number],
  runs: AgentRuns['runs'],
): [label: string, tone: StatusTone] {
  const running = runs.filter((run) => run.agent_id === agent.agent_id && isRunning(run));
  const uncertain = running.find((run) => runState(run) !== run.status);
  if (uncertain) return [stateLabel(runState(uncertain)), liveStatusTone(runState(uncertain))];
  if (running.length) return [`${running.length} running`, 'running'];
  if (agent.status === 'monitored') return ['Idle', 'neutral'];
  if (agent.status === 'unregistered') return ['Unregistered', 'neutral'];
  return ['Not monitored', 'neutral'];
}

function Roster({
  runs,
  stats,
  now,
}: {
  runs: AgentRuns;
  stats: AgentRunStats | undefined;
  now: number;
}) {
  const byAgent = new Map(stats?.agents.map((agent) => [agent.agent_id, agent]));
  return (
    <Surface padding="none" clip>
      <ScrollArea axis="x">
        <Table density="dense" aria-label="Agent roster">
          <TableHeader>
            <TableRow>
              <TableHead scope="col">Agent</TableHead>
              <TableHead scope="col">State</TableHead>
              <TableHead scope="col">Last run</TableHead>
              <TableHead scope="col">14 days</TableHead>
              <TableHead scope="col" numeric>
                Runs · 7d
              </TableHead>
              <TableHead scope="col" numeric>
                Cost · 7d
              </TableHead>
              <TableHead scope="col" numeric>
                p50 duration
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.coverage.map((agent) => {
              const [label, tone] = runs.store.available
                ? rosterState(agent, runs.runs)
                : (['Unknown', 'neutral'] as const);
              const stat = byAgent.get(agent.agent_id);
              const last = stat?.last_run;
              return (
                <TableRow key={agent.agent_id}>
                  <TableCell>
                    {agent.status === 'unregistered' ? (
                      <Text as="strong" size="sm">
                        {agent.name}
                      </Text>
                    ) : (
                      <Link
                        to={`/agents/${encodeURIComponent(agent.agent_id)}`}
                        variant="subtle"
                        title={agent.detail}
                      >
                        {agent.name}
                      </Link>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge tone={tone}>{label}</StatusBadge>
                  </TableCell>
                  <TableCell>
                    {last ? (
                      <Cluster gap="stack" wrap={false}>
                        <StatusDot
                          tone={liveStatusTone(last.status)}
                          label={stateLabel(last.status)}
                        />
                        <Link
                          to={`/agents/runs/${encodeURIComponent(last.id)}`}
                          variant="subtle"
                          title={last.label ?? last.id}
                        >
                          <RelativeTime value={last.started_at} now={now} />
                        </Link>
                      </Cluster>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    {stat ? (
                      <MiniStackedBars
                        ariaLabel={`${agent.name} runs per day, 14 days`}
                        labels={stat.daily.map((day) => day.date)}
                        series={[
                          {
                            key: 'succeeded',
                            label: 'Succeeded',
                            color: chartStatusColor('success'),
                            values: stat.daily.map((day) => day.succeeded),
                          },
                          {
                            key: 'failed',
                            label: 'Failed',
                            color: chartStatusColor('critical'),
                            values: stat.daily.map((day) => day.failed),
                          },
                          {
                            key: 'other',
                            label: 'Other',
                            color: chartStatusColor('neutral'),
                            values: stat.daily.map((day) => day.other),
                          },
                        ]}
                        height={24}
                        width={112}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell
                    numeric
                    detail={stat?.failed_7d ? `${stat.failed_7d} failed` : undefined}
                  >
                    {stat ? stat.runs_7d : '—'}
                  </TableCell>
                  <TableCell numeric>{stat ? formatCost(stat.cost_7d) : '—'}</TableCell>
                  <TableCell numeric>{formatDuration(stat?.p50_elapsed_seconds_7d)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </ScrollArea>
    </Surface>
  );
}

// --------------------------------------------------------------------------- #
// Dashboard
// --------------------------------------------------------------------------- #

export function AgentsLiveDashboard() {
  const query = useAgentRuns();
  const stats = useAgentRunStats();
  const defaultModels = useDefaultModels();
  const data = query.data;
  const ticking = !query.isError && (data?.runs ?? []).some(isRunning);
  const now = useNow({ live: ticking });
  const offset = data && ticking ? Math.max(0, (now - query.dataUpdatedAt) / 1000) : 0;
  const connection = query.isError
    ? data
      ? 'Disconnected · stale data'
      : 'Disconnected'
    : isLoadingData(query)
      ? 'Connecting'
      : !data?.store.available
        ? 'Store unavailable'
        : 'Live';

  return (
    <Stack gap="section">
      <Stack gap="heading">
        <Cluster justify="between">
          <span role="status">
            <StatusBadge tone={query.isError ? 'critical' : 'success'}>{connection}</StatusBadge>
          </span>
          <Button
            variant="control"
            size="sm"
            disabled={isLoadingData(query)}
            onClick={() => {
              void query.refetch();
              void stats.refetch();
            }}
          >
            Refresh
          </Button>
        </Cluster>
        {isLoadingData(query) ? (
          <LoadingSkeleton variant="table" count={4} label="Loading agent runs" />
        ) : !data ? (
          <Stack gap="stack">
            <StateMessage state="error">Unable to load agents.</StateMessage>
            <Cluster>
              <Button variant="control" size="sm" onClick={() => void query.refetch()}>
                Retry
              </Button>
            </Cluster>
          </Stack>
        ) : (
          <>
            {data.store.available ? null : (
              <StateMessage state="error">Run store unavailable · {data.store.detail}</StateMessage>
            )}
            <HeaderStrip runs={data} stats={stats.data} now={now} />
          </>
        )}
      </Stack>
      {data ? (
        <>
          <TerminalSection title="Agents">
            <Roster runs={data} stats={stats.data} now={now} />
          </TerminalSection>
          <TerminalSection title="Runs">
            <RunsTable
              runs={data.runs}
              showAgent
              defaultModels={defaultModels}
              now={now}
              offset={offset}
              label="Agent runs"
            />
          </TerminalSection>
        </>
      ) : null}
    </Stack>
  );
}
