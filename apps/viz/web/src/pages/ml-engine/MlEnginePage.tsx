/**
 * Live, read-only ML Engine training-run workspace.
 *
 * USAGE:
 *   Routed at /ml-engine and optionally /ml-engine?run=<run-id>.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';

import { useMlEngineProducers, useMlEngineRun, useMlEngineRuns } from '@/lib/api/mlEngine';
import {
  Banner,
  Cluster,
  Columns,
  CopyButton,
  ErrorPanel,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  liveStatusTone,
  PageHeader,
  ProgressBar,
  pluralize,
  ScrollArea,
  SectionWorkspace,
  Stack,
  StatGrid,
  StatItem,
  StatusBadge,
  StepStrip,
  Surface,
  Text,
  useSearchParamsPatch,
} from '@/ui';

import { MlEngineNavigator } from './MlEngineNavigator';
import { MlEngineOverview } from './MlEngineOverview';
import {
  artifactLabel,
  completionSummary,
  elapsedDuration,
  matchesFilters,
  progressLabel,
  type RunFilter,
  relativeAge,
  selectRunId,
  visibleStages,
} from './model';

// --------------------------------------------------------------------------- #
// Constants and helpers
// --------------------------------------------------------------------------- #

function timestampLabel(value: string | null): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value));
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ');
}

// --------------------------------------------------------------------------- #
// Selected run detail
// --------------------------------------------------------------------------- #

function RunDetail({ detail }: { detail: NonNullable<ReturnType<typeof useMlEngineRun>['data']> }) {
  const { run, artifact } = detail;
  const stages = visibleStages(run);
  const currentStage = stages.indexOf(run.stage);
  const completion = completionSummary(artifact);

  return (
    <article key={run.run_id}>
      <PageHeader
        title={run.run_id}
        subtitle={`${run.producer} · started ${timestampLabel(run.started_at)}${
          run.completed_at ? ` · completed ${timestampLabel(run.completed_at)}` : ''
        }`}
        right={
          <Cluster gap="stack">
            <StatusBadge tone={liveStatusTone(run.status)} bordered dot={false}>
              {run.status}
            </StatusBadge>
            <CopyButton value={run.run_id} label="Copy run ID" variant="control" />
          </Cluster>
        }
      />

      <Surface
        as="section"
        variant="panel"
        padding="gutter"
        rules="block-end"
        tinted
        aria-labelledby="ml-progress-title"
      >
        <Stack gap="block">
          <Cluster justify="between" gap="stack" align="end">
            <Stack gap="xs" className="min-w-0">
              <span id="ml-progress-title">
                <Text variant="eyebrow">Validation fits</Text>
              </span>
              <Text as="strong" size="base" weight="medium" className="break-words">
                {run.operation}
              </Text>
            </Stack>
            <Text variant="data" size="lg">
              {progressLabel(run)}
            </Text>
          </Cluster>
          <Stack gap="stack">
            <ProgressBar
              value={run.completed_fits}
              max={run.total_fits}
              label="Completed validation fits"
            />
            <Text as="p" variant="caption">
              {run.candidate ?? 'Candidate pending'}
              {run.candidate_index && run.candidate_count
                ? ` · candidate ${run.candidate_index} of ${run.candidate_count}`
                : ''}
              {run.fold_index && run.fold_count
                ? ` · fold ${run.fold_index} of ${run.fold_count}`
                : ''}
            </Text>
          </Stack>
          <StepStrip
            label="Training stages"
            current={currentStage}
            items={stages.map((stage) => ({ id: stage, label: titleCase(stage) }))}
          />
        </Stack>
      </Surface>

      <Surface variant="panel" padding="gutter" rules="block-end">
        <Columns template="repeat(2, minmax(0,1fr))" from="md" gap="section">
          <Stack as="section" gap="heading" aria-label="Execution">
            <Text as="h2" variant="eyebrow">
              Execution
            </Text>
            <StatGrid variant="rows">
              <StatItem label="Task" value={run.task ?? '—'} />
              <StatItem label="Target" value={run.target ?? '—'} />
              <StatItem label="Features" value={run.feature_count ?? '—'} />
              <StatItem label="Host" value={run.host ?? '—'} />
              <StatItem label="Elapsed" value={elapsedDuration(run)} />
              <StatItem label="Last update" value={relativeAge(run.updated_at)} />
            </StatGrid>
          </Stack>
          <Stack as="section" gap="heading" aria-label="Artifact">
            <Text as="h2" variant="eyebrow">
              Artifact
            </Text>
            <StatusBadge
              tone={run.inference_ready ? 'success' : 'neutral'}
              dot={false}
              className="min-h-6 self-start"
            >
              {artifactLabel(run, artifact !== null)}
            </StatusBadge>
            <StatGrid variant="rows">
              <StatItem
                label="Final refit"
                value={run.final_refit === null ? '—' : String(run.final_refit)}
              />
              <StatItem label="Inference ready" value={String(run.inference_ready)} />
              <StatItem label="Path" value={artifact?.path ?? `db/ml-engine/${run.run_id}`} />
            </StatGrid>
          </Stack>
        </Columns>
      </Surface>

      {run.error ? (
        <Surface
          as="section"
          variant="panel"
          padding="gutter"
          rules="block-end"
          aria-label="Failure"
        >
          <Stack gap="heading">
            <Text as="h2" variant="eyebrow">
              Failure
            </Text>
            <ErrorPanel message={`${run.error.type}: ${run.error.message}`} />
          </Stack>
        </Surface>
      ) : null}

      {completion.selection.length > 0 || completion.metrics.length > 0 ? (
        <Surface
          as="section"
          variant="panel"
          padding="gutter"
          rules="block-end"
          aria-label="Results"
        >
          <Stack gap="heading">
            <Text as="h2" variant="eyebrow">
              Results
            </Text>
            <Columns template="repeat(2, minmax(0,1fr))" from="md" gap="section">
              {completion.selection.length > 0 ? (
                <Stack gap="xs">
                  <Text variant="eyebrow">Selection</Text>
                  <StatGrid variant="rows">
                    {completion.selection.map(([label, value]) => (
                      <StatItem key={label} label={label} value={value ?? '—'} />
                    ))}
                  </StatGrid>
                </Stack>
              ) : null}
              {completion.metrics.length > 0 ? (
                <Stack gap="xs">
                  <Text variant="eyebrow">Metrics</Text>
                  <StatGrid variant="rows">
                    {completion.metrics.map(([label, value]) => (
                      <StatItem key={label} label={label} value={value ?? '—'} />
                    ))}
                  </StatGrid>
                </Stack>
              ) : null}
            </Columns>
          </Stack>
        </Surface>
      ) : null}
    </article>
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

export function MlEnginePage() {
  const [searchParams] = useSearchParams();
  const patchSearchParams = useSearchParamsPatch();
  const [filter, setFilter] = useState<RunFilter>('all');
  const [producerFilter, setProducerFilter] = useState<string>('all');
  // The API owns filtering: the run list is a bounded newest-first page, so a
  // client-side filter would only ever see the top of the store.
  const runsQuery = useMlEngineRuns({
    producer: producerFilter === 'all' ? undefined : producerFilter,
    status: filter === 'all' ? undefined : filter,
  });
  const producersQuery = useMlEngineProducers();
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data?.runs]);
  const requestedRunId = searchParams.get('run');
  const selectedRunId = selectRunId(requestedRunId);
  const detailQuery = useMlEngineRun(selectedRunId);
  const selectedRun = detailQuery.data?.run;
  const indexedRuns =
    selectedRun &&
    !runs.some((run) => run.run_id === selectedRun.run_id) &&
    matchesFilters(selectedRun, filter, producerFilter)
      ? [selectedRun, ...runs]
      : runs;
  const filtersActive = filter !== 'all' || producerFilter !== 'all';
  const totalRunCount = runsQuery.data?.count ?? runs.length;
  const invalidCount = runsQuery.data?.invalid_count ?? 0;

  useEffect(() => {
    if (requestedRunId && !selectedRunId) patchSearchParams({ run: null }, { replace: true });
  }, [patchSearchParams, requestedRunId, selectedRunId]);

  useEffect(() => {
    if (selectedRun && !matchesFilters(selectedRun, filter, producerFilter)) {
      patchSearchParams({ run: null }, { replace: true });
    }
  }, [filter, patchSearchParams, producerFilter, selectedRun]);

  const chooseRun = (runId: string) => {
    patchSearchParams({ run: runId });
  };

  return (
    <SectionWorkspace
      contentMode="fill"
      navigator={
        <MlEngineNavigator
          runs={indexedRuns}
          totalRunCount={totalRunCount}
          selectedRunId={selectedRunId}
          filter={filter}
          producers={producersQuery.data?.producers ?? []}
          producerFilter={producerFilter}
          isLoading={isLoadingData(runsQuery)}
          hasError={runsQuery.isError && !runsQuery.data}
          onFilterChange={setFilter}
          onProducerChange={setProducerFilter}
          onSelectRun={chooseRun}
        />
      }
    >
      {selectedRunId ? (
        <Stack gap="none" className="h-full min-h-0">
          {invalidCount > 0 ? (
            <Banner tone="info">
              {invalidCount} malformed run {pluralize(invalidCount, 'sidecar')} omitted
            </Banner>
          ) : null}
          <ScrollArea fill>
            {isLoadingData(detailQuery) ? (
              <Inset padding="md">
                <LoadingSkeleton count={10} />
              </Inset>
            ) : detailQuery.data ? (
              <>
                {detailQuery.error ? (
                  <Banner tone="warning">
                    Refresh failed, showing the last loaded run: {detailQuery.error.message}
                  </Banner>
                ) : null}
                <RunDetail detail={detailQuery.data} />
              </>
            ) : detailQuery.error ? (
              <ErrorPanel
                message={`Unable to load selected run: ${detailQuery.error.message}`}
                onRetry={() => void detailQuery.refetch()}
              />
            ) : null}
          </ScrollArea>
        </Stack>
      ) : (
        <MlEngineOverview
          runs={runs}
          totalCount={totalRunCount}
          invalidCount={invalidCount}
          loading={isLoadingData(runsQuery)}
          error={runsQuery.isError && !runsQuery.data}
          filtersActive={filtersActive}
        />
      )}
    </SectionWorkspace>
  );
}
