/**
 * One run, end to end: header facts and links, a step timeline grouped by stage, and a
 * step list beside the selected step's usage, report, error and activity. A reviewed run
 * shows the meta-analyst's report inline.
 *
 * USAGE:
 *   Routed at /agents/runs/:runId.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { TimelineChart, type TimelineRow } from '@quant-factory/qf-ui/charts/renderers';
import { chartStatusColor } from '@quant-factory/qf-ui/charts/theme';
import { useMemo, useState } from 'react';
import { useParams } from 'react-router';
import {
  type AgentRun,
  type AgentStep,
  useAgentRunActivity,
  useAgentRunSteps,
  useAgentStepReport,
} from '@/lib/api/agent-runs';
import type { DocPage } from '@/lib/api/docs';
import {
  Badge,
  Button,
  Cluster,
  Columns,
  EmptyState,
  FacetedFilter,
  formatDuration,
  Identifier,
  Inset,
  isLoadingData,
  Link,
  LoadingSkeleton,
  liveStatusTone,
  RelativeTime,
  ScrollArea,
  SegmentedControl,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  StatusBadge,
  StatusDot,
  Surface,
  TerminalPage,
  TerminalSection,
  Text,
  Timestamp,
  TokenUsage,
} from '@/ui';
import { SanitizedMarkdown } from '../docs/SanitizedMarkdown';
import {
  agentName,
  binding,
  formatCost,
  isActive,
  runHref,
  runState,
  runTitle,
  stateLabel,
} from './runs';

// --------------------------------------------------------------------------- #
// Timeline model
// --------------------------------------------------------------------------- #

type Shade = 'status' | 'cost' | 'duration';

const STAGE_COLLAPSE = 20;

function stepStart(step: AgentStep): number {
  return step.started_at ? Date.parse(step.started_at) : Number.NaN;
}

function stepEnd(step: AgentStep, now: number): number {
  if (step.finished_at) return Date.parse(step.finished_at);
  if (step.elapsed_seconds !== null) return stepStart(step) + step.elapsed_seconds * 1000;
  return now;
}

/** Steps ordered by stage (first start) then start; a stage over 20 steps is one row. */
function timelineRows(steps: AgentStep[], shade: Shade, now: number): TimelineRow[] {
  const timed = steps.filter((step) => Number.isFinite(stepStart(step)));
  const stages = new Map<string, AgentStep[]>();
  for (const step of [...timed].sort((a, b) => stepStart(a) - stepStart(b))) {
    stages.set(step.name, [...(stages.get(step.name) ?? []), step]);
  }
  const totalCost = timed.reduce((sum, step) => sum + (step.cost_usd ?? 0), 0);
  const totalTime = timed.reduce((sum, step) => sum + (step.elapsed_seconds ?? 0), 0);
  const shadeColor = (status: string, cost: number, seconds: number) => {
    if (shade === 'status') return chartStatusColor(liveStatusTone(status));
    const share = shade === 'cost' ? cost / (totalCost || 1) : seconds / (totalTime || 1);
    if (share >= 0.75) return chartStatusColor('critical');
    if (share >= 0.5) return chartStatusColor('warning');
    return chartStatusColor('neutral');
  };
  const share = (cost: number, seconds: number) =>
    shade === 'cost'
      ? `${Math.round((cost / (totalCost || 1)) * 100)}% of cost`
      : shade === 'duration'
        ? `${Math.round((seconds / (totalTime || 1)) * 100)}% of step time`
        : undefined;
  return [...stages].flatMap(([name, items]) => {
    if (items.length > STAGE_COLLAPSE) {
      const cost = items.reduce((sum, step) => sum + (step.cost_usd ?? 0), 0);
      const seconds = items.reduce((sum, step) => sum + (step.elapsed_seconds ?? 0), 0);
      const failed = items.some((step) => step.status === 'failed');
      const running = items.some((step) => step.status === 'running' || step.status === 'checking');
      return [
        {
          id: `stage:${name}`,
          label: `${name} (${items.length} steps)`,
          start: Math.min(...items.map(stepStart)),
          end: Math.max(...items.map((step) => stepEnd(step, now))),
          color: shadeColor(running ? 'running' : failed ? 'failed' : 'succeeded', cost, seconds),
          detail: share(cost, seconds),
        },
      ];
    }
    return items.map((step) => ({
      id: step.id,
      label: step.work_item ? `${name} · ${step.work_item}` : name,
      start: stepStart(step),
      end: stepEnd(step, now),
      color: shadeColor(step.status, step.cost_usd ?? 0, step.elapsed_seconds ?? 0),
      detail: [stateLabel(step.status), share(step.cost_usd ?? 0, step.elapsed_seconds ?? 0)]
        .filter(Boolean)
        .join(' · '),
    }));
  });
}

// --------------------------------------------------------------------------- #
// Header
// --------------------------------------------------------------------------- #

function RunHeader({ run }: { run: AgentRun }) {
  const state = runState(run);
  const totals = run.totals;
  return (
    <Stack gap="heading">
      <Cluster gap="stack">
        <Link to="/agents" variant="subtle">
          Agents
        </Link>
        <Text as="span" variant="caption">
          /
        </Text>
        <Link to={`/agents/${encodeURIComponent(run.agent_id)}?view=runs`} variant="subtle">
          {agentName(run.agent_id)}
        </Link>
        <Text as="span" variant="caption">
          /
        </Text>
        <Text as="span" variant="data" tone="muted">
          <Identifier value={run.id} truncate="none" copyable />
        </Text>
      </Cluster>
      <StatGrid variant="strip" boxed aria-label="Run facts">
        <StatItem
          label="Status"
          value={
            <span title={run.health_detail ?? undefined}>
              <StatusBadge tone={liveStatusTone(state)}>{stateLabel(state)}</StatusBadge>
            </span>
          }
        />
        <StatItem
          label="Started"
          value={<Timestamp value={run.started_at ?? ''} precision="second" timeZone="local" />}
        />
        <StatItem
          label="Finished"
          value={
            run.finished_at ? (
              <Timestamp value={run.finished_at} precision="second" timeZone="local" />
            ) : (
              '—'
            )
          }
        />
        <StatItem label="Duration" value={formatDuration(run.elapsed_seconds)} />
        <StatItem
          label="Cost"
          value={formatCost(totals?.cost_usd, totals?.cost_complete ?? true)}
          delta={totals?.cost_complete === false ? 'some steps unpriced' : undefined}
          deltaTone="muted"
        />
        <StatItem
          label="Tokens"
          value={
            <TokenUsage
              input={totals?.input_tokens}
              output={totals?.output_tokens}
              cacheRead={totals?.cache_read_tokens}
              cacheWrite={totals?.cache_write_tokens}
              reasoning={totals?.thinking_tokens}
            />
          }
        />
        {run.attempt ? (
          <StatItem label="Attempt" value={`${run.attempt.number} of ${run.attempt.count}`} />
        ) : null}
      </StatGrid>
      {run.resumed_from_run_id ||
      run.subject ||
      run.reviews.length ||
      run.agent_id === 'strategy-optimizer' ? (
        <Cluster gap="block">
          {run.resumed_from_run_id ? (
            <Link to={runHref(run.resumed_from_run_id)} variant="inline">
              Resumed from the previous attempt
            </Link>
          ) : null}
          {run.subject ? (
            <Text as="span" size="sm">
              Review of{' '}
              <Link to={runHref(run.subject.id)} variant="inline">
                {run.subject.label ?? run.subject.target ?? run.subject.id}
              </Link>
            </Text>
          ) : null}
          {run.reviews.map((review, index) => (
            <Link key={review.id} to={runHref(review.id)} variant="inline">
              {index ? `Review ${index + 1}` : 'Meta-analyst review'}
            </Link>
          ))}
          {run.agent_id === 'strategy-optimizer' ? (
            <Link
              to={`/agents/strategy-optimizer/runs/${encodeURIComponent(run.id)}`}
              variant="inline"
            >
              Optimizer files and documents
            </Link>
          ) : null}
        </Cluster>
      ) : null}
      {run.error ? <StateMessage state="error">{run.error}</StateMessage> : null}
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Selected step
// --------------------------------------------------------------------------- #

type StepTab = 'report' | 'error' | 'activity';
type ActivityQuery = ReturnType<typeof useAgentRunActivity>;

function reportPage(step: AgentStep, text: string): DocPage {
  return {
    path: step.artifacts?.directory ?? step.id,
    title: step.name,
    markdown: text,
    modified: null,
    generated: false,
  };
}

function StepReport({ step }: { step: AgentStep }) {
  const available = step.artifacts?.report_available ?? false;
  const report = useAgentStepReport(step.run_id, step.id, available);
  if (!available) return <EmptyState title="No report for this step." />;
  if (isLoadingData(report)) {
    return <LoadingSkeleton variant="line" count={6} label="Loading report" />;
  }
  if (report.isError || !report.data) {
    return (
      <StateMessage compact state="error">
        Report unavailable.
      </StateMessage>
    );
  }
  return (
    <Stack gap="stack">
      <SanitizedMarkdown page={reportPage(step, report.data.text)} />
      {report.data.truncated ? (
        <Text as="p" variant="caption">
          Preview truncated. The full report is in the step folder.
        </Text>
      ) : null}
    </Stack>
  );
}

function StepActivity({ query, step }: { query: ActivityQuery; step: AgentStep }) {
  const [sources, setSources] = useState<string[]>([]);
  const activity = query.data;
  if (isLoadingData(query)) {
    return <LoadingSkeleton variant="line" count={6} label="Loading activity" />;
  }
  if (query.error && !activity) {
    return (
      <StateMessage compact state="error">
        Activity unavailable.
      </StateMessage>
    );
  }
  if (!activity?.available) return <EmptyState title="No activity feed for this run." />;
  const entries = activity.entries.filter((entry) => entry.step_id === step.id);
  const shown = entries.filter((entry) => sources.length === 0 || sources.includes(entry.source));
  const counts = new Map<string, number>();
  for (const entry of entries) counts.set(entry.source, (counts.get(entry.source) ?? 0) + 1);
  return (
    <Stack gap="stack">
      <Cluster gap="stack">
        <FacetedFilter
          title="Source"
          options={[...counts].map(([value, count]) => ({ value, label: value, count }))}
          selected={sources}
          onSelectedChange={setSources}
        />
      </Cluster>
      {shown.length === 0 ? (
        <EmptyState title="No activity recorded for this step." />
      ) : (
        <Stack gap="none">
          {shown.map((entry, index) => (
            <Inset key={`${entry.at}-${index}`} padding="sm">
              <Columns template="6rem 5rem minmax(0,1fr)" gap="stack">
                <Text as="span" variant="data" tone="muted">
                  <Timestamp value={entry.at} precision="second" timeZone="local" />
                </Text>
                <Text as="span" variant="caption">
                  {entry.source}
                </Text>
                <Text as="span" size="sm" className="break-words whitespace-pre-wrap">
                  {entry.text}
                </Text>
              </Columns>
            </Inset>
          ))}
        </Stack>
      )}
      {activity.truncated ? (
        <Text as="p" variant="caption">
          Recent activity only: the feed keeps the latest {activity.entries.length} entries of the
          run.
        </Text>
      ) : null}
    </Stack>
  );
}

function StepPanel({ step, activity }: { step: AgentStep; activity: ActivityQuery }) {
  const [tab, setTab] = useState<StepTab>(step.error ? 'error' : 'report');
  return (
    <Surface padding="md">
      <Stack gap="block">
        <Stack gap="stack">
          <Cluster justify="between">
            <Cluster gap="stack">
              <Text as="h3" variant="label">
                {step.work_item ? `${step.name} · ${step.work_item}` : step.name}
              </Text>
              <StatusBadge tone={liveStatusTone(step.status)}>
                {stateLabel(step.status)}
              </StatusBadge>
            </Cluster>
            {step.model ? (
              <Badge size="sm" variant="ghost">
                {[step.engine, binding(step)].filter(Boolean).join(' · ')}
              </Badge>
            ) : step.engine ? (
              <Badge size="sm" variant="ghost">
                {step.engine}
              </Badge>
            ) : null}
          </Cluster>
          <StatGrid variant="inline" aria-label="Step facts">
            <StatItem
              label="Started"
              value={step.started_at ? <RelativeTime value={step.started_at} /> : '—'}
            />
            <StatItem label="Duration" value={formatDuration(step.elapsed_seconds)} />
            <StatItem
              label="Tokens"
              value={
                <TokenUsage
                  input={step.input_tokens}
                  output={step.output_tokens}
                  cacheRead={step.cache_read_tokens}
                  cacheWrite={step.cache_write_tokens}
                  reasoning={step.thinking_tokens}
                />
              }
            />
            <StatItem
              label="Cost"
              value={formatCost(step.cost_usd)}
              delta={step.cost_basis ?? undefined}
              deltaTone="muted"
            />
            {step.completed_units !== null ? (
              <StatItem
                label="Progress"
                value={
                  step.total_units === null
                    ? `${step.completed_units}`
                    : `${step.completed_units}/${step.total_units}`
                }
              />
            ) : null}
          </StatGrid>
        </Stack>
        <SegmentedControl
          variant="tabs"
          size="sm"
          ariaLabel="Step detail"
          value={tab}
          onValueChange={setTab}
          options={[
            { value: 'report', label: 'Report' },
            { value: 'error', label: step.error ? 'Error' : 'No error' },
            { value: 'activity', label: 'Activity' },
          ]}
        />
        {tab === 'report' ? (
          <StepReport step={step} />
        ) : tab === 'error' ? (
          step.error ? (
            <StateMessage state="error">
              <Text as="span" size="sm" className="whitespace-pre-wrap">
                {step.error}
              </Text>
            </StateMessage>
          ) : (
            <EmptyState title="This step recorded no error." />
          )
        ) : (
          <StepActivity query={activity} step={step} />
        )}
      </Stack>
    </Surface>
  );
}

// --------------------------------------------------------------------------- #
// Review
// --------------------------------------------------------------------------- #

function ReviewReport({ reviewId }: { reviewId: string }) {
  const detail = useAgentRunSteps(reviewId);
  const step = detail.data?.steps.find((item) => item.artifacts?.report_available);
  if (isLoadingData(detail)) {
    return <LoadingSkeleton variant="line" count={4} label="Loading review" />;
  }
  if (detail.error && !detail.data) {
    return (
      <StateMessage compact state="error">
        Review unavailable.
      </StateMessage>
    );
  }
  if (!step) return <EmptyState title="The review has no report yet." />;
  return <StepReport step={step} />;
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

export function RunPage() {
  const runId = useParams().runId ?? '';
  return <RunContent key={runId} runId={runId} />;
}

function RunContent({ runId }: { runId: string }) {
  const detail = useAgentRunSteps(runId);
  const run = detail.data?.run;
  const running = run ? isActive(run) : false;
  const activity = useAgentRunActivity(runId, running, 100);
  const [shade, setShade] = useState<Shade>('status');
  const [statuses, setStatuses] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [now] = useState(() => Date.now());
  const steps = useMemo(
    () =>
      [...(detail.data?.steps ?? [])].sort(
        (a, b) => (Date.parse(a.started_at ?? '') || 0) - (Date.parse(b.started_at ?? '') || 0),
      ),
    [detail.data?.steps],
  );
  const rows = useMemo(() => timelineRows(steps, shade, now), [steps, shade, now]);

  if (isLoadingData(detail)) {
    return (
      <TerminalPage title="Run">
        <Stack gap="section">
          <LoadingSkeleton variant="card" count={4} label="Loading run" />
          <LoadingSkeleton variant="chart" announce={false} />
        </Stack>
      </TerminalPage>
    );
  }
  if (!run || !detail.data) {
    return (
      <TerminalPage title="Run">
        <Stack gap="stack">
          <StateMessage state="error">Run {runId} is unavailable.</StateMessage>
          <Cluster>
            <Button variant="control" size="sm" onClick={() => void detail.refetch()}>
              Retry
            </Button>
          </Cluster>
        </Stack>
      </TerminalPage>
    );
  }

  const failed = steps.find((step) => step.status === 'failed');
  const selected = steps.find((step) => step.id === selectedId) ?? failed ?? steps.at(-1) ?? null;
  const listed = steps.filter((step) => statuses.length === 0 || statuses.includes(step.status));
  const counts = new Map<string, number>();
  for (const step of steps) counts.set(step.status, (counts.get(step.status) ?? 0) + 1);

  return (
    <TerminalPage title={runTitle(run)}>
      <Stack gap="section">
        <RunHeader run={run} />
        {rows.length ? (
          <TerminalSection
            title="Timeline"
            right={
              <SegmentedControl
                size="xs"
                ariaLabel="Timeline shading"
                value={shade}
                onValueChange={setShade}
                options={[
                  { value: 'status', label: 'Status' },
                  { value: 'cost', label: 'Share of cost' },
                  { value: 'duration', label: 'Share of time' },
                ]}
              />
            }
          >
            <TimelineChart
              ariaLabel="Step timeline"
              rows={rows}
              selected={selected?.id ?? null}
              onSelect={(id) => {
                if (!id.startsWith('stage:')) setSelectedId(id);
              }}
              formatDuration={(seconds) => formatDuration(seconds)}
            />
          </TerminalSection>
        ) : null}
        <TerminalSection
          title={
            detail.data.step_total > steps.length
              ? `Steps · first ${steps.length} of ${detail.data.step_total}`
              : `Steps · ${detail.data.step_total}`
          }
        >
          {steps.length === 0 ? (
            <EmptyState title="No steps recorded." />
          ) : (
            <Columns template="minmax(16rem,22rem) minmax(0,1fr)" from="lg">
              <Stack gap="stack">
                <FacetedFilter
                  title="Status"
                  options={[...counts].map(([value, count]) => ({
                    value,
                    label: stateLabel(value),
                    count,
                  }))}
                  selected={statuses}
                  onSelectedChange={setStatuses}
                />
                <Surface padding="none" clip>
                  <ScrollArea maxHeight="36rem">
                    {listed.map((step) => (
                      <Button
                        key={step.id}
                        variant="nav"
                        className={step.id === selected?.id ? 'is-selected' : undefined}
                        aria-current={step.id === selected?.id ? 'true' : undefined}
                        onClick={() => setSelectedId(step.id)}
                      >
                        <Cluster gap="stack" wrap={false} className="min-w-0">
                          <StatusDot
                            tone={liveStatusTone(step.status)}
                            label={stateLabel(step.status)}
                          />
                          <Stack gap="none" className="min-w-0">
                            <Text as="span" size="sm" className="block truncate">
                              {step.work_item ? `${step.name} · ${step.work_item}` : step.name}
                            </Text>
                            <Text as="span" variant="caption">
                              {[formatDuration(step.elapsed_seconds), formatCost(step.cost_usd)]
                                .filter((part) => part !== '—')
                                .join(' · ') || '—'}
                            </Text>
                          </Stack>
                        </Cluster>
                      </Button>
                    ))}
                  </ScrollArea>
                </Surface>
              </Stack>
              {selected ? (
                <StepPanel key={selected.id} step={selected} activity={activity} />
              ) : (
                <EmptyState title="Select a step." />
              )}
            </Columns>
          )}
        </TerminalSection>
        {run.reviews[0] ? (
          <TerminalSection
            title="Meta-analyst review"
            right={
              <Link to={runHref(run.reviews[0].id)} variant="subtle">
                Open review run →
              </Link>
            }
          >
            <Surface padding="md">
              <ReviewReport reviewId={run.reviews[0].id} />
            </Surface>
          </TerminalSection>
        ) : null}
      </Stack>
    </TerminalPage>
  );
}
