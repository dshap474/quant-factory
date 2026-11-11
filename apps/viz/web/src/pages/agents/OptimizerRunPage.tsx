/** Dedicated optimizer attempt workspace with stages, files and activity.
 * USAGE: /agents/strategy-optimizer/runs/:runId
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
// --------------------------------------------------------------------------- #
// Imports and compact presentation
// --------------------------------------------------------------------------- #
import { useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { type AgentStep, useAgentRunActivity } from '@/lib/api/agent-runs';
import {
  type OptimizerFileScope,
  useOptimizerAttempts,
  useOptimizerRun,
} from '@/lib/api/optimizer';
import {
  Banner,
  Button,
  Cluster,
  Field,
  formatDuration,
  formatShortDateTime,
  Inset,
  isLoadingData,
  Link,
  LoadingSkeleton,
  liveStatusTone,
  ScrollArea,
  SegmentedControl,
  SelectControl,
  Stack,
  StateMessage,
  StatGrid,
  StatItem,
  StatusBadge,
  Surface,
  TerminalPage,
  Text,
  Toolbar,
} from '@/ui';
import { optimizerStates, outcomeLabel } from './OptimizerOverview';
import { fileScopes, OptimizerRunFiles } from './OptimizerRunFiles';
import { isActive, runState } from './runs';

const stageOrder = ['author', 'audit', 'seal'];
const count = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
function inputTokens(step: AgentStep) {
  const usage = step.artifacts?.usage;
  if (usage?.input_tokens == null) return null;
  return (
    usage.input_tokens +
    (step.engine === 'claude'
      ? (usage.cache_read_tokens ?? 0) + (usage.cache_write_tokens ?? 0)
      : 0)
  );
}

function Activity({ runId, live }: { runId: string; live: boolean }) {
  const query = useAgentRunActivity(runId, live);
  return (
    <>
      <Surface padding="none" clip className="flex min-h-0 flex-1 flex-col">
        <ScrollArea fill label="Run activity">
          {isLoadingData(query) ? (
            <LoadingSkeleton variant="table" count={8} />
          ) : query.error && !query.data ? (
            <StateMessage state="error">Activity unavailable.</StateMessage>
          ) : !query.data?.entries.length ? (
            <StateMessage>No activity recorded.</StateMessage>
          ) : (
            <Table density="dense">
              <TableHeader sticky>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Activity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...query.data.entries].reverse().map((entry, index) => (
                  <TableRow key={`${entry.at}-${index}`}>
                    <TableCell>
                      <time dateTime={entry.at}>
                        <Text as="span" variant="data">
                          {new Date(entry.at).toLocaleTimeString()}
                        </Text>
                      </time>
                    </TableCell>
                    <TableCell>{entry.source}</TableCell>
                    <TableCell wrap>{entry.text}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </ScrollArea>
      </Surface>
      {query.data?.truncated && (
        <Inset padding="sm">
          <Text as="p" variant="caption">
            Recent activity only. The full activity.jsonl is available in Attempt files.
          </Text>
        </Inset>
      )}
    </>
  );
}

// --------------------------------------------------------------------------- #
// Route and workspace
// --------------------------------------------------------------------------- #
export function OptimizerRunPage() {
  const runId = useParams().runId ?? '';
  return <RunWorkspace key={runId} runId={runId} />;
}
function RunWorkspace({ runId }: { runId: string }) {
  const query = useOptimizerRun(runId);
  const [attemptPage, setAttemptPage] = useState(0);
  const attempts = useOptimizerAttempts(
    runId,
    attemptPage * 10,
    !!query.data && isActive(query.data.detail.run),
  );
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const from: unknown = location.state?.from;
  const back =
    typeof from === 'string' && /^\/agents\/strategy-optimizer(?:\?|$)/.test(from)
      ? from
      : '/agents/strategy-optimizer?view=runs';
  const entry = query.data;
  const run = entry?.detail.run;
  const scope: OptimizerFileScope =
    fileScopes.find((item) => item.value === params.get('scope'))?.value ??
    (entry && !entry.file_roots?.version ? 'attempt' : 'version');
  const activity = params.get('tab') === 'activity';
  const defaultFile = entry?.document_paths?.outcome ?? entry?.document_paths?.spec ?? null;
  const path = params.has('file')
    ? params.get('file') || null
    : params.has('scope')
      ? null
      : defaultFile;
  const directory = params.get('directory') ?? path?.split('/').slice(0, -1).join('/') ?? '';
  const selectFile = (nextScope: OptimizerFileScope, nextPath: string | null, folder?: string) => {
    setParams(
      { scope: nextScope, file: nextPath ?? '', ...(folder ? { directory: folder } : {}) },
      { replace: true, state: { from: back } },
    );
  };
  const orderedSteps = [...(entry?.detail.steps ?? [])].sort(
    (a, b) => stageOrder.indexOf(a.name) - stageOrder.indexOf(b.name),
  );
  return (
    <TerminalPage
      fill
      title={run?.target ?? 'Optimizer run'}
      right={
        <Cluster gap="heading">
          <Link to={back} variant="subtle">
            Run history
          </Link>
          {entry?.research.surface_url ? (
            <Link to={entry.research.surface_url} variant="subtle">
              Research results
            </Link>
          ) : null}
        </Cluster>
      }
    >
      <Inset padding="md" className="flex min-h-0 min-w-0 flex-1 flex-col">
        <Stack gap="heading" className="min-h-0 min-w-0 flex-1">
          {isLoadingData(query) ? (
            <LoadingSkeleton variant="table" count={8} />
          ) : !entry || !run ? (
            <StateMessage state="error">
              Run unavailable. Return to the optimizer to choose another run.
            </StateMessage>
          ) : (
            <>
              <StatGrid variant="strip" columns={4} aria-label="Run summary">
                <StatItem
                  label="Execution"
                  value={
                    <StatusBadge tone={liveStatusTone(runState(run))}>
                      {optimizerStates[runState(run)] ?? run.status}
                    </StatusBadge>
                  }
                />
                <StatItem
                  label="Research outcome"
                  value={
                    <Text as="span" variant="data">
                      {outcomeLabel(entry)}
                    </Text>
                  }
                />
                <StatItem
                  label="Duration"
                  value={
                    <Text as="span" variant="data">
                      {formatDuration(run.elapsed_seconds)}
                    </Text>
                  }
                />
                <StatItem
                  label="Started"
                  value={
                    <Text as="span" variant="data">
                      {formatShortDateTime(run.started_at, 'Not recorded')}
                    </Text>
                  }
                />
              </StatGrid>
              <Cluster justify="between">
                <Cluster gap="stack">
                  <Field
                    label={`Attempt · ${entry.attempt_count}`}
                    htmlFor="optimizer-attempt"
                    layout="inline"
                  >
                    <SelectControl
                      id="optimizer-attempt"
                      ariaLabel="Select attempt"
                      value={runId}
                      options={[
                        ...(attempts.data?.attempts.some((item) => item.run.id === runId)
                          ? []
                          : [
                              {
                                value: runId,
                                label: `${formatShortDateTime(run.started_at, 'Not recorded')} · ${runId.slice(0, 8)}`,
                              },
                            ]),
                        ...(attempts.data?.attempts ?? []).map((item) => ({
                          value: item.run.id,
                          label: `${formatShortDateTime(item.run.started_at, 'Not recorded')} · ${optimizerStates[item.run.status]} · ${item.run.id.slice(0, 8)}`,
                        })),
                      ]}
                      onValueChange={(id) =>
                        navigate(`/agents/strategy-optimizer/runs/${encodeURIComponent(id)}`, {
                          state: { from: back },
                        })
                      }
                    />
                  </Field>
                  {isLoadingData(attempts) && (
                    <LoadingSkeleton variant="line" className="w-32" label="Loading attempts" />
                  )}
                </Cluster>
                {entry.attempt_count > 10 && (
                  <Cluster gap="stack">
                    <Button
                      icon
                      variant="control"
                      aria-label="Newer attempts"
                      disabled={attemptPage === 0}
                      onClick={() => setAttemptPage(attemptPage - 1)}
                    >
                      ‹
                    </Button>
                    <Button
                      icon
                      variant="control"
                      aria-label="Older attempts"
                      disabled={(attemptPage + 1) * 10 >= entry.attempt_count}
                      onClick={() => setAttemptPage(attemptPage + 1)}
                    >
                      ›
                    </Button>
                  </Cluster>
                )}
              </Cluster>
              {(run.error || attempts.isError) && (
                <StateMessage state="error" compact>
                  {run.error ?? 'Attempt history unavailable.'}
                </StateMessage>
              )}
              {query.error && (
                <Banner tone="warning">
                  Refresh failed, showing the last loaded run: {query.error.message}
                </Banner>
              )}
              <Surface padding="none" clip>
                <ScrollArea axis="both" maxHeight="12rem" label="Stage execution">
                  <Table density="dense" className="min-w-[850px]">
                    <TableHeader sticky>
                      <TableRow>
                        <TableHead>Stage</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Model</TableHead>
                        <TableHead>Effort</TableHead>
                        <TableHead>Duration</TableHead>
                        <TableHead title="All input tokens, including cache reads and writes">
                          Input · incl. cache
                        </TableHead>
                        <TableHead>Output</TableHead>
                        <TableHead>Reported cost</TableHead>
                        <TableHead>
                          <span className="sr-only">Report</span>
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {stageOrder.map((name, index) => {
                        const step = orderedSteps.find((item) => item.name === name);
                        const inherited =
                          run.resumed_from_run_id &&
                          orderedSteps.length > 0 &&
                          index < stageOrder.indexOf(orderedSteps[0].name);
                        return (
                          <TableRow key={name}>
                            <TableCell>
                              <Cluster gap="stack">
                                <Text as="span" variant="data" tone="muted">
                                  0{index + 1}
                                </Text>
                                <Text as="strong" size="sm">
                                  {name[0].toUpperCase() + name.slice(1)}
                                </Text>
                              </Cluster>
                            </TableCell>
                            <TableCell>
                              {step
                                ? (optimizerStates[step.status] ?? step.status)
                                : inherited
                                  ? 'Earlier attempt'
                                  : 'Not started'}
                            </TableCell>
                            <TableCell>{step?.model ?? '—'}</TableCell>
                            <TableCell>{step?.reasoning ?? '—'}</TableCell>
                            <TableCell>{formatDuration(step?.elapsed_seconds ?? null)}</TableCell>
                            <TableCell
                              numeric
                              title={step ? String(inputTokens(step) ?? 'Not reported') : undefined}
                            >
                              {step ? count(inputTokens(step)) : '—'}
                            </TableCell>
                            <TableCell
                              numeric
                              title={String(step?.artifacts?.usage.output_tokens ?? 'Not reported')}
                            >
                              {count(step?.artifacts?.usage.output_tokens)}
                            </TableCell>
                            <TableCell
                              numeric
                              title={step?.artifacts?.usage.cost_basis ?? 'Cost not reported'}
                            >
                              {step?.artifacts?.usage.cost_usd == null
                                ? '—'
                                : `$${step.artifacts.usage.cost_usd.toFixed(2)}`}
                            </TableCell>
                            <TableCell>
                              {step?.artifacts?.report_available && (
                                <Button
                                  variant="link"
                                  onClick={() =>
                                    selectFile('attempt', `steps/${step.id}/${step.name}.out.md`)
                                  }
                                >
                                  Report ↗
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </ScrollArea>
              </Surface>
              <Toolbar>
                <Cluster justify="between">
                  <SegmentedControl
                    variant="tabs"
                    ariaLabel="Run workspace"
                    value={activity ? 'activity' : 'files'}
                    options={[
                      { value: 'files', label: 'Files' },
                      { value: 'activity', label: 'Activity' },
                    ]}
                    onValueChange={(next) => {
                      const nextParams = new URLSearchParams(params);
                      if (next === 'activity') nextParams.set('tab', 'activity');
                      else nextParams.delete('tab');
                      setParams(nextParams, { replace: true, state: { from: back } });
                    }}
                  />
                  {!activity && (
                    <SelectControl
                      ariaLabel="File location"
                      value={scope}
                      options={fileScopes.filter((item) => entry.file_roots?.[item.value])}
                      onValueChange={(value) => selectFile(value as OptimizerFileScope, null)}
                    />
                  )}
                  <Cluster gap="stack">
                    {(['spec', 'review', 'outcome'] as const)
                      .filter((name) => entry.document_paths?.[name])
                      .map((name) => (
                        <Button
                          key={name}
                          variant="link"
                          onClick={() =>
                            selectFile('version', entry.document_paths?.[name] ?? null)
                          }
                        >
                          {name === 'spec'
                            ? 'Specification'
                            : name === 'review'
                              ? 'Review'
                              : 'Outcome'}
                        </Button>
                      ))}
                  </Cluster>
                </Cluster>
              </Toolbar>
              {activity ? (
                <Activity runId={runId} live={isActive(run)} />
              ) : (
                <OptimizerRunFiles
                  runId={runId}
                  scope={scope}
                  path={path}
                  directory={directory}
                  roots={entry.file_roots ?? {}}
                  live={isActive(run)}
                  onSelect={selectFile}
                />
              )}
            </>
          )}
        </Stack>
      </Inset>
    </TerminalPage>
  );
}
