/**
 * One page layout for every agent: a header strip with default bindings and coverage,
 * runs and cost per day, a stage graph whose nodes filter the runs, and the runs table.
 * The Runs view is the full table plus the agent's own extension, when it has one.
 *
 * USAGE:
 *   <AgentOverview agentId="wiki-ingestor" view="overview" onRuns={showRuns} />
 *   <AgentOverview agentId="strategy-optimizer" view="runs" extension={<OptimizerHistory />} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { StackedTimeChart } from '@quant-factory/qf-ui/charts/renderers';
import { chartStatusColor } from '@quant-factory/qf-ui/charts/theme';
import { ArrowRight } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import {
  type AgentRun,
  type AgentRunStats,
  useAgentRunStats,
  useAgentRuns,
} from '@/lib/api/agent-runs';
import { type AgentSummary, useAgents } from '@/lib/api/agents';
import {
  Button,
  Cluster,
  Columns,
  formatDuration,
  isLoadingData,
  LoadingSkeleton,
  pluralize,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  StatusBadge,
  TerminalSection,
  Text,
  useNow,
} from '@/ui';
import { useDefaultModels } from './AgentsLiveDashboard';
import { RunsTable } from './RunsTable';
import { formatCost, isRunning } from './runs';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

export interface AgentOverviewProps {
  agentId: string;
  view: 'overview' | 'runs';
  onRuns?: () => void;
  /** Agent-specific content shown under the Runs view's table. */
  extension?: ReactNode;
}

type AgentStat = AgentRunStats['agents'][number];

interface StageNode {
  name: string;
  runs: number;
  failed: number;
  p50: number | null;
  cost: number | null;
  models: string[];
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? (sorted[middle] ?? null)
    : ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2;
}

/** Stages in recorded order, then any bound stage never recorded; models from recorded steps. */
export function stageNodes(runs: AgentRun[], agent: AgentSummary | undefined): StageNode[] {
  const nodes = new Map<string, { node: StageNode; elapsed: number[]; models: Set<string> }>();
  const entry = (name: string) => {
    let item = nodes.get(name);
    if (!item) {
      item = {
        node: { name, runs: 0, failed: 0, p50: null, cost: null, models: [] },
        elapsed: [],
        models: new Set(),
      };
      nodes.set(name, item);
    }
    return item;
  };
  for (const run of [...runs].reverse()) {
    for (const stage of run.stages) {
      const item = entry(stage.name);
      item.node.runs += 1;
      if (stage.status === 'failed' || stage.status === 'interrupted') item.node.failed += 1;
      if (stage.elapsed_seconds !== null) item.elapsed.push(stage.elapsed_seconds);
      if (stage.cost_usd !== null) item.node.cost = (item.node.cost ?? 0) + stage.cost_usd;
      for (const model of stage.models) item.models.add(model);
    }
  }
  for (const bound of agent?.bindings ?? []) entry(bound.stage);
  return [...nodes.values()].map(({ node, elapsed, models }) => ({
    ...node,
    p50: median(elapsed),
    models: [...models],
  }));
}

// --------------------------------------------------------------------------- #
// Sections
// --------------------------------------------------------------------------- #

const pendingValue = <LoadingSkeleton variant="line" announce={false} className="w-20" />;

function Header({
  agent,
  coverage,
  stat,
  loading,
}: {
  agent: AgentSummary | undefined;
  coverage: { status: string; detail: string } | undefined;
  stat: AgentStat | undefined;
  loading: { agent: boolean; coverage: boolean; stat: boolean };
}) {
  return (
    <StatGrid variant="strip" boxed aria-label="Agent summary">
      <StatItem
        label="Default bindings"
        value={
          loading.agent ? (
            pendingValue
          ) : agent?.bindings.length ? (
            // Text lines, not badges: a binding outgrows a strip column and must wrap.
            <Stack gap="none">
              {agent.bindings.map((item) => (
                <Text key={item.stage} as="span" size="sm">
                  {[item.stage, item.engine, item.model, item.effort].filter(Boolean).join(' · ')}
                </Text>
              ))}
            </Stack>
          ) : (
            '—'
          )
        }
      />
      <StatItem
        label="Coverage"
        value={
          loading.coverage ? (
            pendingValue
          ) : (
            <span title={coverage?.detail}>
              <StatusBadge tone={coverage?.status === 'monitored' ? 'success' : 'neutral'}>
                {coverage?.status === 'monitored' ? 'Monitored' : 'Not monitored'}
              </StatusBadge>
            </span>
          )
        }
      />
      <StatItem
        label="Runs · 7d"
        value={loading.stat ? pendingValue : stat ? stat.runs_7d : '—'}
        delta={stat?.failed_7d ? `${stat.failed_7d} failed` : undefined}
        deltaTone="negative"
      />
      <StatItem
        label="Cost · 7d"
        value={loading.stat ? pendingValue : stat ? formatCost(stat.cost_7d) : '—'}
      />
      <StatItem
        label="p50 duration · 7d"
        value={loading.stat ? pendingValue : formatDuration(stat?.p50_elapsed_seconds_7d)}
      />
    </StatGrid>
  );
}

function TrendSkeleton() {
  return (
    <Columns template="repeat(2, minmax(0,1fr))" from="lg">
      <TerminalSection title="Runs per day">
        <LoadingSkeleton variant="chart" label="Loading runs per day" />
      </TerminalSection>
      <TerminalSection title="Cost per day">
        <LoadingSkeleton variant="chart" label="Loading cost per day" />
      </TerminalSection>
    </Columns>
  );
}

function Trend({ daily }: { daily: AgentStat['daily'] }) {
  const dates = daily.map((day) => new Date(`${day.date}T00:00:00Z`));
  return (
    <Columns template="repeat(2, minmax(0,1fr))" from="lg">
      <TerminalSection title="Runs per day">
        <StackedTimeChart
          ariaLabel="Runs per day by outcome"
          dates={dates}
          series={[
            {
              key: 'succeeded',
              label: 'Succeeded',
              kind: 'bar',
              stack: 'runs',
              color: chartStatusColor('success'),
              values: daily.map((day) => day.succeeded),
            },
            {
              key: 'failed',
              label: 'Failed',
              kind: 'bar',
              stack: 'runs',
              color: chartStatusColor('critical'),
              values: daily.map((day) => day.failed),
            },
            {
              key: 'other',
              label: 'Other',
              kind: 'bar',
              stack: 'runs',
              color: chartStatusColor('neutral'),
              values: daily.map((day) => day.other),
            },
          ]}
        />
      </TerminalSection>
      <TerminalSection title="Cost per day">
        <StackedTimeChart
          ariaLabel="Recorded cost per day"
          dates={dates}
          yFormat={(value) => `$${value.toFixed(value < 1 ? 3 : 2)}`}
          series={[
            {
              key: 'cost',
              label: 'Cost',
              kind: 'bar',
              values: daily.map((day) => day.cost_usd),
            },
          ]}
        />
      </TerminalSection>
    </Columns>
  );
}

function StageGraph({
  nodes,
  selected,
  onSelect,
}: {
  nodes: StageNode[];
  selected: string | null;
  onSelect: (name: string | null) => void;
}) {
  if (nodes.length === 0) return null;
  return (
    <TerminalSection title="Stages">
      <Cluster gap="stack">
        {nodes.map((node, index) => (
          <Cluster key={node.name} gap="stack" wrap={false}>
            {index ? <ArrowRight aria-hidden="true" size={14} /> : null}
            <Button
              variant="nav"
              className={selected === node.name ? 'is-selected' : undefined}
              aria-pressed={selected === node.name}
              onClick={() => onSelect(selected === node.name ? null : node.name)}
            >
              <Stack gap="none">
                <Text as="strong" size="sm">
                  {node.name}
                </Text>
                <Text as="span" variant="caption">
                  {[
                    `${node.runs} ${pluralize(node.runs, 'run')}`,
                    node.runs ? `${Math.round((node.failed / node.runs) * 100)}% failed` : null,
                    node.p50 === null ? null : `p50 ${formatDuration(node.p50)}`,
                    node.cost === null ? null : formatCost(node.cost),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
                {node.models.length ? (
                  <Text as="span" variant="caption">
                    {node.models.join(', ')}
                  </Text>
                ) : null}
              </Stack>
            </Button>
          </Cluster>
        ))}
      </Cluster>
    </TerminalSection>
  );
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

export function AgentOverview({ agentId, view, onRuns, extension }: AgentOverviewProps) {
  const runs = useAgentRuns({ agentId });
  const stats = useAgentRunStats();
  const agents = useAgents();
  const defaultModels = useDefaultModels();
  const [stage, setStage] = useState<string | null>(null);
  const data = runs.data;
  const ticking = !runs.isError && (data?.runs ?? []).some(isRunning);
  const now = useNow({ live: ticking });
  const offset = data && ticking ? Math.max(0, (now - runs.dataUpdatedAt) / 1000) : 0;
  const agent = agents.data?.agents.find((item) => item.id === agentId);
  const stat = stats.data?.agents.find((item) => item.agent_id === agentId);
  const coverage = data?.coverage.find((item) => item.agent_id === agentId);
  const agentRuns = data?.runs.filter((run) => run.agent_id === agentId) ?? [];
  const shown = stage
    ? agentRuns.filter((run) => run.stages.some((item) => item.name === stage))
    : agentRuns;

  const loading = isLoadingData(runs);
  const table = loading ? (
    <LoadingSkeleton variant="table" count={5} label="Loading runs" />
  ) : !data ? (
    <Stack gap="stack">
      <StateMessage state="error">Runs unavailable.</StateMessage>
      <Cluster>
        <Button variant="control" size="sm" onClick={() => void runs.refetch()}>
          Retry
        </Button>
      </Cluster>
    </Stack>
  ) : (
    <RunsTable
      key={stage ?? 'all'}
      runs={shown}
      defaultModels={defaultModels}
      now={now}
      offset={offset}
      label={`${agent?.name ?? agentId} runs`}
      {...(view === 'overview' ? { limit: 10, onViewAll: onRuns } : {})}
    />
  );

  if (view === 'runs') {
    return (
      <Stack gap="section">
        <TerminalSection title="Runs">{table}</TerminalSection>
        {extension}
      </Stack>
    );
  }
  return (
    <Stack gap="section">
      <Header
        agent={agent}
        coverage={coverage}
        stat={stat}
        loading={{ agent: isLoadingData(agents), coverage: loading, stat: isLoadingData(stats) }}
      />
      {isLoadingData(stats) ? <TrendSkeleton /> : stat ? <Trend daily={stat.daily} /> : null}
      {loading ? (
        <TerminalSection title="Stages">
          <LoadingSkeleton variant="line" count={3} label="Loading stages" />
        </TerminalSection>
      ) : (
        <StageGraph nodes={stageNodes(agentRuns, agent)} selected={stage} onSelect={setStage} />
      )}
      <TerminalSection
        title={stage ? `Runs through ${stage}` : 'Recent runs'}
        right={
          stage ? (
            <Button variant="control" size="sm" onClick={() => setStage(null)}>
              Show all stages
            </Button>
          ) : undefined
        }
      >
        {table}
      </TerminalSection>
    </Stack>
  );
}
