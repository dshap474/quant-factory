/**
 * The one agent runs table: running rows pinned first, a stage bar per run, right-aligned
 * figures, agent/status/model filter chips, a peek row with the error and an "Open run"
 * link, and typed empty states.
 *
 * USAGE:
 *   <RunsTable runs={runs} showAgent now={now} offset={offset} />
 *   <RunsTable runs={runs} defaultModels={['gpt-6-luna']} limit={10} onViewAll={showRuns} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Fragment, useState } from 'react';
import type { AgentRun } from '@/lib/api/agent-runs';
import {
  Badge,
  Button,
  Cluster,
  EmptyState,
  FacetedFilter,
  formatDuration,
  Identifier,
  Inset,
  Link,
  liveStatusTone,
  RelativeTime,
  ScrollArea,
  Stack,
  StageBar,
  StateMessage,
  StatusBadge,
  Surface,
  Text,
  TokenUsage,
} from '@/ui';
import {
  agentName,
  formatCost,
  isActive,
  isRunning,
  runHref,
  runModels,
  runState,
  runTitle,
  stageSegments,
  stateLabel,
} from './runs';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RunsTableProps {
  runs: AgentRun[];
  /** Adds the Agent column and facet (the Live Dashboard). */
  showAgent?: boolean;
  /** Default models per agent; a run's model shows only when it differs. */
  defaultModels?: ReadonlyMap<string, ReadonlySet<string>>;
  /** Clock for relative start times. */
  now: number;
  /** Seconds since the data was fetched, added to live elapsed times. */
  offset?: number;
  /** Show only the first rows with a "View all runs" control. */
  limit?: number;
  onViewAll?: () => void;
  /** Accessible table caption. */
  label: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function elapsed(run: AgentRun, offset: number): string {
  if (isActive(run) && ['unknown', 'interrupted'].includes(run.health)) return '—';
  return formatDuration(
    run.elapsed_seconds === null ? null : run.elapsed_seconds + (isActive(run) ? offset : 0),
  );
}

function options(values: string[], label: (value: string) => string = (value) => value) {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts]
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, label: label(value), count }));
}

// --------------------------------------------------------------------------- #
// Rows
// --------------------------------------------------------------------------- #

function RunLabel({ run, models }: { run: AgentRun; models: string[] }) {
  return (
    <Stack gap="none">
      <Link to={runHref(run.id)} variant="subtle" title={runTitle(run)}>
        <Text as="span" size="sm" className="block max-w-[30ch] truncate">
          {runTitle(run)}
        </Text>
      </Link>
      <Cluster gap="stack" wrap={false}>
        <Text as="span" variant="data" tone="muted">
          <Identifier value={run.id} truncate="middle" copyable />
        </Text>
        {run.host_id ? (
          <Badge size="sm" variant="ghost">
            {run.host_id}
          </Badge>
        ) : null}
        {run.attempt && run.attempt.count > 1 ? (
          <Badge size="sm" variant="ghost">
            {`Attempt ${run.attempt.number}/${run.attempt.count}`}
          </Badge>
        ) : null}
        {run.reviews[0] ? (
          <Link
            to={runHref(run.reviews[0].id)}
            variant="subtle"
            title="Open the meta-analyst review"
          >
            <Badge size="sm" tone="info">
              Reviewed
            </Badge>
          </Link>
        ) : null}
        {models.map((model) => (
          <Badge key={model} size="sm" variant="ghost">
            {model}
          </Badge>
        ))}
      </Cluster>
    </Stack>
  );
}

function RunPeek({ run }: { run: AgentRun }) {
  return (
    <Inset padding="sm">
      <Stack gap="stack">
        {run.stages.length ? (
          <Cluster gap="block">
            {run.stages.map((stage) => (
              <StatusBadge key={stage.name} tone={liveStatusTone(stage.status)}>
                {`${stage.name} · ${stage.count} · ${formatDuration(stage.elapsed_seconds)}`}
              </StatusBadge>
            ))}
          </Cluster>
        ) : null}
        {run.subject ? (
          <Text as="span" variant="caption">
            Review of{' '}
            <Link to={runHref(run.subject.id)} variant="inline">
              {run.subject.label ?? run.subject.target ?? run.subject.id}
            </Link>
          </Text>
        ) : null}
        {run.error ? (
          <StateMessage compact state="error">
            {run.error}
          </StateMessage>
        ) : null}
        {run.health_detail && runState(run) !== run.status ? (
          <Text as="span" variant="caption">
            {run.health_detail}
          </Text>
        ) : null}
        <Cluster justify="end">
          <Link to={runHref(run.id)} variant="control" size="sm">
            Open run →
          </Link>
        </Cluster>
      </Stack>
    </Inset>
  );
}

// --------------------------------------------------------------------------- #
// Table
// --------------------------------------------------------------------------- #

export function RunsTable({
  runs,
  showAgent = false,
  defaultModels,
  now,
  offset = 0,
  limit,
  onViewAll,
  label,
}: RunsTableProps) {
  const [agents, setAgents] = useState<string[]>([]);
  const [states, setStates] = useState<string[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const filtered = runs.filter(
    (run) =>
      (agents.length === 0 || agents.includes(run.agent_id)) &&
      (states.length === 0 || states.includes(runState(run))) &&
      (models.length === 0 || runModels(run).some((model) => models.includes(model))),
  );
  // Running rows first; the API already orders the rest newest first.
  const ordered = [...filtered.filter(isRunning), ...filtered.filter((run) => !isRunning(run))];
  const shown = limit === undefined ? ordered : ordered.slice(0, limit);
  const filtering = agents.length + states.length + models.length > 0;
  const clear = () => {
    setAgents([]);
    setStates([]);
    setModels([]);
  };
  const columns = showAgent ? 8 : 7;

  return (
    <Stack gap="stack">
      <Cluster gap="stack">
        {showAgent ? (
          <FacetedFilter
            title="Agent"
            options={options(
              runs.map((run) => run.agent_id),
              agentName,
            )}
            selected={agents}
            onSelectedChange={setAgents}
          />
        ) : null}
        <FacetedFilter
          title="Status"
          options={options(runs.map(runState), stateLabel)}
          selected={states}
          onSelectedChange={setStates}
        />
        <FacetedFilter
          title="Model"
          options={options(runs.flatMap(runModels))}
          selected={models}
          onSelectedChange={setModels}
        />
        {filtering ? (
          <Button variant="control" size="sm" onClick={clear}>
            Clear filters
          </Button>
        ) : null}
      </Cluster>
      {runs.length === 0 ? (
        <EmptyState
          title="No runs recorded yet."
          hint="Runs appear here as soon as an agent starts."
        />
      ) : shown.length === 0 ? (
        <Stack gap="stack">
          <EmptyState title="No runs match these filters." />
          <Cluster>
            <Button variant="control" size="sm" onClick={clear}>
              Clear filters
            </Button>
          </Cluster>
        </Stack>
      ) : (
        <Surface padding="none" clip>
          <ScrollArea axis="x">
            <Table density="dense" aria-label={label}>
              <TableHeader sticky>
                <TableRow>
                  <TableHead scope="col">Status</TableHead>
                  <TableHead scope="col">Run</TableHead>
                  {showAgent ? <TableHead scope="col">Agent</TableHead> : null}
                  <TableHead scope="col">Stages</TableHead>
                  <TableHead scope="col" numeric>
                    Duration
                  </TableHead>
                  <TableHead scope="col" numeric>
                    Cost
                  </TableHead>
                  <TableHead scope="col" numeric>
                    Tokens
                  </TableHead>
                  <TableHead scope="col" numeric>
                    Started
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shown.map((run) => {
                  const open = expanded === run.id;
                  const state = runState(run);
                  const defaults = defaultModels?.get(run.agent_id);
                  const extraModels = defaults?.size
                    ? runModels(run).filter((model) => !defaults.has(model))
                    : [];
                  const Chevron = open ? ChevronDown : ChevronRight;
                  return (
                    <Fragment key={run.id}>
                      <TableRow aria-selected={open || undefined}>
                        <TableCell>
                          <Cluster gap="stack" wrap={false}>
                            <Button
                              variant="plain"
                              size="xs"
                              icon
                              aria-expanded={open}
                              aria-label={open ? 'Hide run peek' : 'Peek at run'}
                              onClick={() => setExpanded(open ? null : run.id)}
                            >
                              <Chevron aria-hidden="true" size={14} />
                            </Button>
                            <span title={run.health_detail ?? undefined}>
                              <StatusBadge tone={liveStatusTone(state)}>
                                {stateLabel(state)}
                              </StatusBadge>
                            </span>
                          </Cluster>
                        </TableCell>
                        <TableCell>
                          <RunLabel run={run} models={extraModels} />
                        </TableCell>
                        {showAgent ? (
                          <TableCell>
                            <Link
                              to={`/agents/${encodeURIComponent(run.agent_id)}`}
                              variant="subtle"
                            >
                              {agentName(run.agent_id)}
                            </Link>
                          </TableCell>
                        ) : null}
                        <TableCell>
                          {run.stages.length ? (
                            <StageBar
                              label={`${runTitle(run)} stages`}
                              segments={stageSegments(run)}
                            />
                          ) : (
                            <Text as="span" variant="caption">
                              —
                            </Text>
                          )}
                        </TableCell>
                        <TableCell numeric>{elapsed(run, offset)}</TableCell>
                        <TableCell numeric>
                          {formatCost(run.totals?.cost_usd, run.totals?.cost_complete ?? true)}
                        </TableCell>
                        <TableCell numeric>
                          <TokenUsage
                            input={run.totals?.input_tokens}
                            output={run.totals?.output_tokens}
                          />
                        </TableCell>
                        <TableCell numeric>
                          <RelativeTime value={run.started_at} now={now} />
                        </TableCell>
                      </TableRow>
                      {open ? (
                        <TableRow data-table-group="">
                          <TableCell colSpan={columns} fullBleed>
                            <RunPeek run={run} />
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollArea>
        </Surface>
      )}
      {limit !== undefined && ordered.length > limit && onViewAll ? (
        <Cluster justify="end">
          <Button variant="control" size="sm" onClick={onViewAll}>
            {`View all ${ordered.length} runs →`}
          </Button>
        </Cluster>
      ) : null}
    </Stack>
  );
}
