/**
 * Strategy memory-version page — preregistration records, research surface or saved runs.
 *
 * USAGE:
 *   Routed at /strategies/:type/:memoryVersion
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { DataTable } from '@quant-factory/qf-ui/tables';
import { useQuery } from '@tanstack/react-query';
import { Suspense, useCallback, useMemo } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router';
import {
  strategyCompositionPanel,
  strategyCurrentDataReplay,
  strategyRedirect,
  strategyTradePanel,
} from '@/extensions';
import { STALE } from '@/lib/api/stale-times';
import {
  getVersionFinal,
  getVersionRuns,
  getVersionSurface,
  strategyKeys,
  useStrategyVersions,
} from '@/lib/api/strategies';
import { useStrategyVersionRecords } from '@/lib/api/strategy-version-records';
import { EquityCurve } from '@/lib/components/charts/EquityCurve';
import { CompositionPending } from '@/lib/components/strategies/CompositionPending';
import {
  EmptyState,
  ErrorPanel,
  familyName,
  formatPercent,
  isLoadingData,
  LoadingSkeleton,
  lazyNamed,
  PageHeader,
  PageShell,
  SegmentedControl,
  TerminalPage,
  TerminalSection,
  Text,
  useSearchParamsPatch,
} from '@/ui';

const InvalidatedStrategyVersion = lazyNamed(
  () => import('./InvalidatedStrategyVersion'),
  'InvalidatedStrategyVersion',
);

const ResearchStrategySurface = lazyNamed(
  () => import('@/lib/components/strategies/ResearchStrategySurface'),
  'ResearchStrategySurface',
);

const StrategyVersionDetails = lazyNamed(
  () => import('@/lib/components/strategies/StrategyVersionDetails'),
  'StrategyVersionDetails',
);

const SingleAssetStrategySurface = lazyNamed(
  () => import('@/lib/components/strategies/SingleAssetStrategySurface'),
  'SingleAssetStrategySurface',
);

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const PortfolioDiagnostics = lazyNamed(
  () => import('@/lib/components/strategies/PortfolioDiagnostics'),
  'PortfolioDiagnostics',
);

type VersionView = 'trades' | 'overview' | 'composition' | 'details' | 'portfolio-diagnostics';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StrategyVersionPage() {
  const { type: strategyType = '', memoryVersion = '' } = useParams();
  const [searchParams] = useSearchParams();
  const patchParams = useSearchParamsPatch();
  const viewParam = searchParams.get('view');
  // `single-asset` and `asset` are the tab's former URL names; old links still land here.
  const versionView: VersionView =
    viewParam === 'composition' || viewParam === 'single-asset'
      ? 'composition'
      : viewParam === 'details' || viewParam === 'portfolio-diagnostics' || viewParam === 'trades'
        ? viewParam
        : 'overview';
  const assetsParam = searchParams.get('assets') ?? searchParams.get('asset') ?? '';
  const selectedAssets = useMemo(() => assetsParam.split(',').filter(Boolean), [assetsParam]);
  const selectedConfig = searchParams.get('config');
  const setVersionView = (view: VersionView) => {
    patchParams({ view });
  };
  const setSelectedAssets = useCallback(
    (assets: string[], replace = false) => {
      patchParams({ view: 'composition', asset: null, assets: assets.join(',') }, { replace });
    },
    [patchParams],
  );
  // One header for every tab and state: sector kicker, then family name / version.
  const family = familyName(strategyType);
  const kicker = family.sector ?? undefined;
  const title = `${family.name} / ${memoryVersion}`;
  const versionViewTabs = (
    <SegmentedControl
      variant="tabs"
      ariaLabel="Strategy version view"
      options={[
        { value: 'overview', label: 'Overview' },
        { value: 'composition', label: 'Composition' },
        { value: 'trades', label: 'Trades' },
        { value: 'details', label: 'Details' },
        { value: 'portfolio-diagnostics', label: 'Portfolio diagnostics' },
      ]}
      value={versionView}
      onValueChange={setVersionView}
    />
  );

  // Redirect targets computed before hooks so hook enable flags stay stable.
  const redirect = strategyRedirect(strategyType, memoryVersion);
  const currentDataReplay = strategyCurrentDataReplay(strategyType, memoryVersion);
  const skipVersionFetches = redirect !== null;

  // Share cache with the Strategies navigator / StrategyTypePage (same versions key).
  const versionsQuery = useStrategyVersions(skipVersionFetches ? '' : strategyType);
  const versionMeta =
    versionsQuery.data?.find((item) => item.memory_version === memoryVersion) ?? null;
  const versionMetaReady = versionsQuery.isSuccess || skipVersionFetches;
  // The view tabs lead the header while the version loads and once it is known, so the
  // header keeps its geometry; a missing version shows only the title.
  const tabs = versionMeta || isLoadingData(versionsQuery) ? versionViewTabs : undefined;
  const header = <PageHeader kicker={kicker} title={title} tabs={tabs} />;
  const versionExists = versionsQuery.isSuccess && versionMeta != null;
  const recordQuery = useStrategyVersionRecords(
    versionExists && !versionMeta?.has_surface ? strategyType : '',
    memoryVersion,
  );
  // Any `*_diagnostic` study kind records evidence without a portfolio account.
  const studyKind: unknown = recordQuery.data?.record.study_kind;
  const diagnosticOnly = typeof studyKind === 'string' && studyKind.endsWith('_diagnostic');
  const isResearch = versionMeta?.source === 'research';
  const isInvalidated = versionMeta?.state === 'invalidated';
  const hasResearchSurface = isResearch && versionMeta?.has_surface === true;
  const operatorBaseline = versionsQuery.data?.find(
    (item) => item.display_state === 'baseline' && item.source === 'research' && item.has_surface,
  );
  const operatorBaselineVersion =
    operatorBaseline?.memory_version === memoryVersion
      ? null
      : (operatorBaseline?.memory_version ?? null);

  const surfaceQuery = useQuery({
    queryKey: strategyKeys.surface(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionSurface(strategyType, memoryVersion, signal),
    staleTime: STALE.list,
    enabled: Boolean(
      strategyType && memoryVersion && versionExists && hasResearchSurface && !isInvalidated,
    ),
    retry: false,
  });

  const operatorBaselineSurfaceQuery = useQuery({
    queryKey: strategyKeys.surface(strategyType, operatorBaselineVersion ?? ''),
    queryFn: ({ signal }) => getVersionSurface(strategyType, operatorBaselineVersion ?? '', signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType && operatorBaselineVersion && hasResearchSurface),
    retry: false,
  });

  const currentDataReplaySurfaceQuery = useQuery({
    queryKey: strategyKeys.surface(strategyType, currentDataReplay?.sourceVersion ?? ''),
    queryFn: ({ signal }) =>
      getVersionSurface(strategyType, currentDataReplay?.sourceVersion ?? '', signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType && currentDataReplay && hasResearchSurface),
    retry: false,
  });

  const finalQuery = useQuery({
    queryKey: strategyKeys.final(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionFinal(strategyType, memoryVersion, signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType && memoryVersion && versionExists && !isResearch),
    retry: false,
  });

  const runsQuery = useQuery({
    queryKey: strategyKeys.runs(strategyType, memoryVersion),
    queryFn: ({ signal }) => getVersionRuns(strategyType, memoryVersion, signal),
    staleTime: STALE.list,
    enabled: Boolean(strategyType && memoryVersion && versionExists && !isResearch),
    retry: false,
  });

  const final = finalQuery.data ?? null;
  const runs = runsQuery.data ?? [];

  const tableData = runs.map((run) => ({
    preset: run.preset ?? '-',
    run_id: run.run_id,
    total_return: formatPercent(run.metrics?.total_return),
    sortino: run.metrics?.sortino ?? null,
    sharpe: run.metrics?.sharpe ?? null,
    calmar: run.metrics?.calmar ?? null,
    martin: run.metrics?.martin ?? null,
    max_dd: formatPercent(run.metrics?.max_drawdown),
    win_rate: formatPercent(run.metrics?.win_rate),
    created: run.created_at ? run.created_at.replace('T', ' ').slice(0, 19) : '-',
    promoted: run.run_id === final?.selected_run_id ? 'Final' : '',
  }));

  const equityData = (() => {
    if (!final?.data) return [];
    const dateCol = final.columns.find((column) =>
      ['date', 'datetime', 'timestamp'].includes(column.toLowerCase()),
    );
    const equityCol = final.columns.find((column) =>
      ['equity', 'cumulative_return', 'cum_return', 'portfolio_value'].includes(
        column.toLowerCase(),
      ),
    );
    if (!dateCol || !equityCol) return [];
    const startValue = final.data[0]?.[equityCol] as number | undefined;
    if (!startValue) return [];
    return final.data.map((row) => ({
      date: new Date(row[dateCol] as string),
      value: ((row[equityCol] as number) / startValue - 1) * 100,
    }));
  })();

  // An extension may publish a version under a different route (`strategyRedirects`),
  // so redirect before any version fetch renders a page the family does not own.
  if (redirect) {
    return <Navigate replace to={redirect} />;
  }

  // Registered records exist before a version has any published account outputs.
  if (versionView === 'details') {
    return (
      <PageShell>
        {header}
        <Suspense fallback={<LoadingSkeleton variant="chart" />}>
          <StrategyVersionDetails strategyType={strategyType} memoryVersion={memoryVersion} />
        </Suspense>
      </PageShell>
    );
  }

  if (isLoadingData(versionsQuery) || isLoadingData(recordQuery)) {
    return (
      <TerminalPage kicker={kicker} title={title} tabs={tabs}>
        {versionView === 'composition' ? (
          <CompositionPending />
        ) : (
          <LoadingSkeleton variant="chart" />
        )}
      </TerminalPage>
    );
  }

  if (versionsQuery.error && !versionsQuery.data) {
    return (
      <TerminalPage kicker={kicker} title={title} tabs={tabs}>
        <ErrorPanel
          message={versionsQuery.error.message}
          onRetry={() => {
            void versionsQuery.refetch();
          }}
        />
      </TerminalPage>
    );
  }

  if (versionMetaReady && versionMeta == null) {
    return (
      <TerminalPage kicker={kicker} title={title} tabs={tabs}>
        <EmptyState
          title="Version does not exist"
          hint="Pick a version from the strategy nav, or return to the type list."
        />
      </TerminalPage>
    );
  }

  if (diagnosticOnly) {
    const reportPath = recordQuery.data?.record.report_path;
    return (
      <PageShell>
        {header}
        <EmptyState
          title="Diagnostic study · no new account"
          hint={
            typeof recordQuery.data?.record.finding === 'string'
              ? recordQuery.data.record.finding
              : 'This study records diagnostic evidence only. No NAV, holdings or portfolio report is created.'
          }
        />
        {typeof reportPath === 'string' && reportPath.startsWith('/strategies/') ? (
          <Text>
            <Link to={reportPath}>Open diagnostic results</Link>
          </Text>
        ) : null}
      </PageShell>
    );
  }

  if (versionView === 'trades') {
    const adapter = strategyTradePanel(strategyType, memoryVersion);
    const TradePanel = adapter?.component;
    return (
      <PageShell>
        {header}
        {TradePanel ? (
          <Suspense fallback={<LoadingSkeleton variant="chart" />}>
            <TradePanel
              key={`${strategyType}/${memoryVersion}`}
              strategyType={strategyType}
              memoryVersion={memoryVersion}
            />
          </Suspense>
        ) : (
          <EmptyState
            title="Trades unavailable"
            hint="This version has no saved-trade explorer adapter."
          />
        )}
      </PageShell>
    );
  }

  if (versionView === 'portfolio-diagnostics' && versionMeta && !isInvalidated) {
    return (
      <PageShell>
        {header}
        <Suspense fallback={<LoadingSkeleton variant="chart" />}>
          <PortfolioDiagnostics
            key={`${strategyType}/${memoryVersion}/${versionMeta.selected_run_id}/${selectedConfig}`}
            strategyType={strategyType}
            memoryVersion={memoryVersion}
            runId={versionMeta.selected_run_id}
            account={selectedConfig}
          />
        </Suspense>
      </PageShell>
    );
  }

  if (versionView === 'composition' && versionMeta && !isInvalidated) {
    const CompositionPanel = strategyCompositionPanel(strategyType, memoryVersion)?.component;
    return (
      <PageShell>
        {header}
        <Suspense fallback={<CompositionPending />}>
          <SingleAssetStrategySurface
            key={`${strategyType}/${memoryVersion}/${versionMeta.selected_run_id ?? ''}`}
            strategyType={strategyType}
            memoryVersion={memoryVersion}
            selectedRunId={versionMeta.selected_run_id}
            assets={selectedAssets}
            configId={selectedConfig}
            onConfigChange={(configId) =>
              // Another account holds other assets: re-pick its leaders.
              patchParams({ config: configId, assets: null })
            }
            onAssetsChange={setSelectedAssets}
          />
        </Suspense>
        {CompositionPanel ? (
          <Suspense fallback={<LoadingSkeleton variant="chart" />}>
            <CompositionPanel
              key={`${strategyType}/${memoryVersion}/${versionMeta.selected_run_id ?? ''}`}
              strategyType={strategyType}
              memoryVersion={memoryVersion}
              selectedRunId={versionMeta.selected_run_id ?? null}
            />
          </Suspense>
        ) : null}
      </PageShell>
    );
  }

  if (isInvalidated && versionMeta) {
    return (
      <Suspense
        fallback={
          <TerminalPage kicker={kicker} title={title} tabs={tabs}>
            <LoadingSkeleton variant="chart" />
          </TerminalPage>
        }
      >
        <InvalidatedStrategyVersion
          kicker={kicker}
          title={title}
          strategyType={strategyType}
          memoryVersion={memoryVersion}
          version={versionMeta}
          navigation={tabs}
        />
      </Suspense>
    );
  }

  if (isResearch && versionMeta && !versionMeta.has_surface) {
    return (
      <TerminalPage kicker={kicker} title={title} tabs={tabs}>
        <TerminalSection title="version status">
          <Text as="p" tone="muted" size="sm">
            This research version is registered, but it does not have a selected result surface yet.
            It is visible here without implying that a backtest result has been completed.
          </Text>
        </TerminalSection>
      </TerminalPage>
    );
  }

  if (isResearch) {
    if (
      isLoadingData(surfaceQuery) ||
      isLoadingData(operatorBaselineSurfaceQuery) ||
      isLoadingData(currentDataReplaySurfaceQuery)
    ) {
      return (
        <TerminalPage kicker={kicker} title={title} tabs={tabs}>
          <LoadingSkeleton variant="chart" />
        </TerminalPage>
      );
    }
    if (!surfaceQuery.data) {
      return (
        <TerminalPage kicker={kicker} title={title} tabs={tabs}>
          {surfaceQuery.error ? (
            <ErrorPanel
              message={surfaceQuery.error.message}
              onRetry={() => {
                void surfaceQuery.refetch();
              }}
            />
          ) : (
            <EmptyState title="No research surface" hint="This version has no published surface." />
          )}
        </TerminalPage>
      );
    }
    return (
      <Suspense
        fallback={
          <TerminalPage kicker={kicker} title={title} tabs={tabs}>
            <LoadingSkeleton variant="chart" />
          </TerminalPage>
        }
      >
        <PageShell>
          {header}
          <ResearchStrategySurface
            strategyType={strategyType}
            memoryVersion={memoryVersion}
            surface={surfaceQuery.data}
            operatorBaselineVersion={operatorBaselineVersion}
            operatorBaselineSurface={operatorBaselineSurfaceQuery.data}
            currentDataReplay={
              currentDataReplay
                ? {
                    ...currentDataReplay,
                    surface: currentDataReplaySurfaceQuery.data,
                  }
                : undefined
            }
          />
        </PageShell>
      </Suspense>
    );
  }

  return (
    <TerminalPage kicker={kicker} title={title} tabs={tabs}>
      <TerminalSection title="promoted equity curve">
        {isLoadingData(finalQuery) ? (
          <LoadingSkeleton variant="chart" />
        ) : finalQuery.isError ? (
          <ErrorPanel
            message={finalQuery.error.message}
            onRetry={() => {
              void finalQuery.refetch();
            }}
          />
        ) : equityData.length > 0 ? (
          <EquityCurve data={equityData} />
        ) : (
          <EmptyState
            title="No equity curve available"
            hint="No promoted run for this memory version"
          />
        )}
      </TerminalSection>

      <TerminalSection title="saved runs">
        {runsQuery.isError && !runsQuery.data ? (
          <ErrorPanel
            message={runsQuery.error.message}
            onRetry={() => {
              void runsQuery.refetch();
            }}
          />
        ) : tableData.length === 0 && !isLoadingData(runsQuery) ? (
          <EmptyState title="No saved runs found" hint="No saved runs for this memory version" />
        ) : (
          <DataTable
            data={tableData}
            loading={isLoadingData(runsQuery)}
            defaultSort={{ column: 'sortino', direction: 'desc' }}
            columns={[
              'preset',
              'run_id',
              'total_return',
              'sortino',
              'sharpe',
              'calmar',
              'martin',
              'max_dd',
              'win_rate',
              'created',
              'promoted',
            ]}
          />
        )}
      </TerminalSection>
    </TerminalPage>
  );
}
