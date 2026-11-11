/**
 * Inline run evidence: work items with their usage and report, the bounded activity feed
 * and the run's file locations. Used where a run expands in place (attempt lists).
 *
 * USAGE: <RunExpansion run={run} />
 */

// --------------------------------------------------------------------------- #
// Imports and display helpers
// --------------------------------------------------------------------------- #

import { useState } from 'react';
import {
  type AgentRun,
  type AgentStep,
  useAgentRunActivity,
  useAgentRunDetail,
  useAgentStepReport,
} from '@/lib/api/agent-runs';
import {
  Button,
  CodeBlock,
  Disclosure,
  formatDuration,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  liveStatusTone,
  Pagination,
  Stack,
  StateMessage,
  StatusBadge,
  Surface,
  Text,
} from '@/ui';
import { binding, isActive } from './runs';

function timeLabel(value: string | null): string {
  return value
    ? new Date(value).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : 'Unknown';
}

function progress(step: AgentStep | null): string | null {
  if (!step || step.completed_units === null) return null;
  return step.total_units === null
    ? `${step.completed_units}`
    : `${step.completed_units}/${step.total_units}`;
}

// --------------------------------------------------------------------------- #
// Expanded work items and bounded feed
// --------------------------------------------------------------------------- #

function StepEvidence({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(false);
  const report = useAgentStepReport(step.run_id, step.id, open);
  const evidence = step.artifacts;
  if (!evidence) return null;
  const usage = evidence.usage;
  const inputLabel =
    step.engine === 'claude'
      ? 'uncached input tokens'
      : step.engine === 'codex'
        ? 'input tokens (including cache reads)'
        : 'provider-reported input tokens';
  const usageLabel = [
    usage.input_tokens === null ? null : `${usage.input_tokens.toLocaleString()} ${inputLabel}`,
    usage.output_tokens === null ? null : `${usage.output_tokens.toLocaleString()} output tokens`,
    usage.cache_read_tokens === null
      ? null
      : `${usage.cache_read_tokens.toLocaleString()} cache-read input`,
    usage.cache_write_tokens === null
      ? null
      : `${usage.cache_write_tokens.toLocaleString()} cache-write input`,
    usage.thinking_tokens === null ? null : `${usage.thinking_tokens.toLocaleString()} reasoning`,
    usage.cost_usd === null
      ? null
      : `$${usage.cost_usd.toFixed(4)}${usage.cost_basis ? ` (${usage.cost_basis})` : ''}`,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Surface
      as="div"
      variant="inset"
      padding="sm"
      aria-label="Step evidence"
      title={evidence.directory ?? undefined}
      className="min-w-0"
    >
      {usageLabel ? (
        <Text as="span" variant="caption" className="block">
          {usageLabel}
        </Text>
      ) : null}
      {evidence.report_available ? (
        <Button variant="control" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Hide report' : 'View report'}
        </Button>
      ) : null}
      {open && isLoadingData(report) ? (
        <LoadingSkeleton variant="line" count={3} label="Loading report" />
      ) : null}
      {open && report.isError ? (
        <StateMessage compact state="error">
          Report unavailable.
        </StateMessage>
      ) : null}
      {open && report.data ? (
        <>
          <CodeBlock value={report.data.text} />
          {report.data.truncated ? (
            <Text as="span" variant="caption" className="block">
              Preview truncated. Full report is in the step folder.
            </Text>
          ) : null}
        </>
      ) : null}
    </Surface>
  );
}

export function RunExpansion({ run }: { run: AgentRun }) {
  const live = isActive(run);
  const [page, setPage] = useState(0);
  const detail = useAgentRunDetail(run.id, live, page * 12);
  const activity = useAgentRunActivity(run.id, live);
  // Placeholder data keeps the previous totals, so Pagination stays mounted while a page loads.
  const paging = detail.data ? { total: detail.data.step_total, limit: detail.data.limit } : null;
  const activeSteps = detail.data?.run.active_steps ?? run.active_steps;
  const activeIds = new Set(activeSteps.map((step) => step.id));
  const steps = [
    ...activeSteps,
    ...(detail.data?.steps ?? []).filter((step) => !activeIds.has(step.id)),
  ];
  return (
    <Surface
      as="section"
      variant="inset"
      padding="none"
      aria-label="Run detail"
      className="grid gap-0 md:grid-cols-2"
    >
      {(detail.data?.run.error ?? run.error) ? (
        <div className="md:col-span-2">
          <StateMessage compact state="error">
            {detail.data?.run.error ?? run.error}
          </StateMessage>
        </div>
      ) : null}
      <div>
        <Inset padding="sm">
          <Text as="h3" variant="label">
            Work items
          </Text>
        </Inset>
        {detail.isError ? (
          <StateMessage compact state="error">
            Steps unavailable{detail.data ? ' · stale data' : ''}.
          </StateMessage>
        ) : null}
        {isLoadingData(detail) ? (
          <LoadingSkeleton variant="line" count={3} label="Loading steps" />
        ) : steps.length === 0 ? (
          <StateMessage compact>No steps recorded.</StateMessage>
        ) : (
          <Stack gap="none">
            {steps.map((step) => (
              <Inset
                key={step.id}
                padding="sm"
                className="grid grid-cols-[6rem_minmax(0,1fr)] gap-x-2"
              >
                <StatusBadge tone={liveStatusTone(step.status)}>{step.status}</StatusBadge>
                <span>
                  {step.name}
                  {step.work_item ? ` · ${step.work_item}` : ''}
                </span>
                <Text as="span" variant="caption" className="block">
                  {[binding(step), progress(step), formatDuration(step.elapsed_seconds)]
                    .filter((part) => part && part !== '—')
                    .join(' · ')}
                </Text>
                {step.error ? (
                  <StateMessage compact state="error">
                    {step.error}
                  </StateMessage>
                ) : null}
                {step.artifacts ? <StepEvidence step={step} /> : null}
              </Inset>
            ))}
          </Stack>
        )}
        {paging && paging.total > paging.limit ? (
          <Pagination
            page={page + 1}
            pageCount={Math.ceil(paging.total / paging.limit)}
            onPageChange={(next) => setPage(next - 1)}
            label={`${paging.total} steps`}
          />
        ) : null}
      </div>
      <div>
        <Inset padding="sm">
          <Text as="h3" variant="label">
            Recent activity
          </Text>
        </Inset>
        {activity.isError ? (
          <StateMessage compact state="error">
            Activity unavailable{activity.data ? ' · stale data' : ''}.
          </StateMessage>
        ) : null}
        {isLoadingData(activity) ? (
          <LoadingSkeleton variant="line" count={3} label="Loading activity" />
        ) : !activity.data?.available ? (
          <StateMessage compact>No activity feed for this run.</StateMessage>
        ) : activity.data.entries.length === 0 ? (
          <StateMessage compact>No activity recorded yet.</StateMessage>
        ) : (
          <Stack gap="none">
            {activity.data.entries.map((entry, index) => (
              <div key={`${entry.at}-${index}`} className="flex gap-2 p-2">
                <time dateTime={entry.at}>
                  <Text as="span" variant="data" tone="muted">
                    {timeLabel(entry.at)}
                  </Text>
                </time>
                <Text as="span" variant="data" tone="muted" className="shrink-0">
                  {entry.source}
                </Text>
                <span>{entry.text}</span>
              </div>
            ))}
          </Stack>
        )}
      </div>
      {detail.data?.locations?.length ? (
        <Disclosure summary="Files" variant="row" className="md:col-span-2">
          <Stack gap="none">
            {detail.data.locations.map((location) => (
              <Text as="span" variant="data" className="block break-all" key={location.path}>
                {location.label} · {location.path}
              </Text>
            ))}
          </Stack>
        </Disclosure>
      ) : null}
    </Surface>
  );
}
