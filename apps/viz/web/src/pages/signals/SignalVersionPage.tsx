/**
 * Signal version page — lifecycle record plus the version's persisted output.
 *
 * A canonical version (the registered engine persisted under db/signals) renders its latest
 * run in place: the family's chart first, then the run's metadata, config, and preview. A
 * research version renders its registered panel and lifecycle record, plus its published research
 * surface (IC, metrics, quantile returns per arm) when one is selected. Either way the family's
 * registered panel (chart first) leads the body, so the page never stacks text above its
 * first chart.
 *
 * USAGE:
 *   Routed at /signals/:family/:memoryVersion. `?signal=<id>&run=<id>` picks another
 *   persisted run of a canonical version; the latest run is the default.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Suspense } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { signalVersionPanel } from '@/extensions';
import { type SignalRun, useSignalResearchVersions, useSignalRuns } from '@/lib/api/signals';
import { formatPredictionRange } from '@/lib/components/signals/signal-freshness';
import {
  EmptyState,
  ErrorPanel,
  familyName,
  formatIsoDay,
  formatPercent,
  IndexBar,
  IndexList,
  isLoadingData,
  LoadingSkeleton,
  lazyNamed,
  TerminalPage,
  TerminalSection,
  Text,
} from '@/ui';

import { SignalRunView } from './SignalRunView';

const SignalResearchSurface = lazyNamed(
  () => import('@/lib/components/signals/SignalResearchSurface'),
  'SignalResearchSurface',
);

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function runDescription(run: SignalRun): string {
  const parts: string[] = [];
  if (run.metadata?.model_type) parts.push(run.metadata.model_type);
  if (run.metrics?.accuracy != null) parts.push(`acc ${formatPercent(run.metrics.accuracy)}`);
  if (run.metrics?.auc != null) parts.push(`auc ${formatPercent(run.metrics.auc)}`);
  if (run.data_range) {
    parts.push(`${run.data_range.start.split(' ')[0]} → ${run.data_range.end.split(' ')[0]}`);
  }
  const predictions = formatPredictionRange(run.first_prediction, run.latest_prediction);
  if (predictions) parts.push(`predictions ${predictions}`);
  return parts.join(' · ');
}

// --------------------------------------------------------------------------- #
// Persisted runs (canonical versions)
// --------------------------------------------------------------------------- #

interface PersistedRunsProps {
  family: string;
  memoryVersion: string;
  signalIds: readonly string[];
  activeSignalId: string;
  activeRunId: string;
}

function PersistedRuns({
  family,
  memoryVersion,
  signalIds,
  activeSignalId,
  activeRunId,
}: PersistedRunsProps) {
  return (
    <TerminalSection title="persisted runs" right={signalIds.join(' · ')}>
      {signalIds.map((signalId) => (
        <PersistedSignalRuns
          key={signalId}
          family={family}
          memoryVersion={memoryVersion}
          signalId={signalId}
          activeSignalId={activeSignalId}
          activeRunId={activeRunId}
        />
      ))}
    </TerminalSection>
  );
}

function PersistedSignalRuns({
  family,
  memoryVersion,
  signalId,
  activeSignalId,
  activeRunId,
}: Omit<PersistedRunsProps, 'signalIds'> & { signalId: string }) {
  const runsQuery = useSignalRuns(signalId);
  const runs = runsQuery.data ?? [];
  if (isLoadingData(runsQuery)) return <LoadingSkeleton variant="line" count={3} />;
  if (runsQuery.error && !runsQuery.data) {
    return (
      <ErrorPanel
        message={runsQuery.error.message}
        onRetry={() => {
          void runsQuery.refetch();
        }}
      />
    );
  }
  return (
    <IndexList>
      {runs.map((run) => {
        const active = signalId === activeSignalId && run.run_id === activeRunId;
        return (
          <IndexBar
            key={`${signalId}/${run.run_id}`}
            href={`/signals/${family}/${memoryVersion}?signal=${encodeURIComponent(signalId)}&run=${encodeURIComponent(run.run_id)}`}
            monoTitle
            title={`${signalId} · ${run.run_id}`}
            description={runDescription(run)}
            metrics={active ? 'shown above' : formatIsoDay(run.created_at)}
          />
        );
      })}
    </IndexList>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SignalVersionPage() {
  const { family = '', memoryVersion = '' } = useParams();
  const [searchParams] = useSearchParams();
  const query = useSignalResearchVersions(family);
  const version = query.data?.find((item) => item.memory_version === memoryVersion) ?? null;
  const isCanonical = version?.source === 'canonical';
  const specializedPanel = signalVersionPanel(family, memoryVersion);
  // One header for every state: sector kicker, then family name / version.
  const name = familyName(family);
  const kicker = name.sector ?? undefined;
  const title = `${name.name} / ${memoryVersion}`;
  const SpecializedPanel = specializedPanel?.component;

  const requestedSignal = searchParams.get('signal');
  const requestedRun = searchParams.get('run');
  const signalIds = version?.signal_ids ?? [];
  const activeSignalId =
    requestedSignal && signalIds.includes(requestedSignal)
      ? requestedSignal
      : (version?.selected_signal_id ?? signalIds[0] ?? null);
  const activeRunId =
    requestedSignal === activeSignalId && requestedRun
      ? requestedRun
      : (version?.selected_run_id ?? null);

  if (isLoadingData(query)) {
    return (
      <TerminalPage kicker={kicker} title={title}>
        <LoadingSkeleton variant="chart" />
      </TerminalPage>
    );
  }
  if (query.error && !query.data) {
    return (
      <TerminalPage kicker={kicker} title={title}>
        <ErrorPanel
          message={query.error.message}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </TerminalPage>
    );
  }
  if (!version) {
    return (
      <TerminalPage kicker={kicker} title={`${title} not found`}>
        <EmptyState
          title="Version does not exist"
          hint="Pick a version from the signal nav, or return to the family list."
        />
      </TerminalPage>
    );
  }

  const showPersistedRun = isCanonical && activeSignalId !== null && activeRunId !== null;

  return (
    <TerminalPage
      kicker={kicker}
      title={title}
      right={[version.lifecycle_status ?? version.display_state, version.lifecycle_phase]
        .filter(Boolean)
        .join(' · ')}
    >
      {SpecializedPanel ? (
        <Suspense fallback={<LoadingSkeleton variant="chart" />}>
          <SpecializedPanel
            family={family}
            memoryVersion={memoryVersion}
            isCanonical={isCanonical}
            version={version}
          />
        </Suspense>
      ) : null}
      {version.has_surface ? (
        <Suspense fallback={<LoadingSkeleton variant="chart" />}>
          <SignalResearchSurface family={family} memoryVersion={memoryVersion} />
        </Suspense>
      ) : null}
      {showPersistedRun ? (
        <SignalRunView
          signalId={activeSignalId}
          runId={activeRunId}
          showChart={SpecializedPanel === undefined}
        />
      ) : null}
      {version.has_surface ? null : (
        <TerminalSection title={isCanonical ? 'registered engine' : 'latest attempt'}>
          <Text as="p" tone="muted" size="sm">
            {showPersistedRun ? (
              <>
                <Link to={`/signals/${family}/${memoryVersion}`}>{activeSignalId}</Link>
                {` · ${activeRunId} · ${version.latest_run ?? 'time unavailable'}`}
              </>
            ) : version.selected_run_id ? (
              `${version.experiment ?? (isCanonical ? 'production' : 'experiment')} · ${version.selected_run_id} · ${version.latest_run ?? 'time unavailable'}`
            ) : (
              `No persisted ${isCanonical ? 'run' : 'attempt'} has been recorded for this version.`
            )}
          </Text>
          {version.invalidation_reason ? (
            <Text as="p" tone="muted" size="sm">
              {version.invalidation_reason}
            </Text>
          ) : null}
          <Text as="p" tone="muted" size="sm">
            {isCanonical
              ? 'This is the registered engine version persisted under db/signals.'
              : 'This research version is registered from its canonical VERSION.toml lifecycle record. Persisted attempts remain immutable under db/research/signals and do not imply promotion.'}
          </Text>
        </TerminalSection>
      )}
      {showPersistedRun ? (
        <PersistedRuns
          family={family}
          memoryVersion={memoryVersion}
          signalIds={signalIds}
          activeSignalId={activeSignalId}
          activeRunId={activeRunId}
        />
      ) : null}
    </TerminalPage>
  );
}
