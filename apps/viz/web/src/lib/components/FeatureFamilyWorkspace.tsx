/**
 * Family overview of the full published panel and consistent snapshot projections.
 *
 * Every visual comes from the shared `@/ui` frame: terminal sections, bounded
 * scroll regions, tables, stat rows and fields. The workspace fills the bounded
 * pane its host gives it (`SectionWorkspace contentMode="fill"`).
 *
 * Strategy presets are not offered here: the workspace always shows the family's
 * full panel. Separately published versions are reached through the navigator.
 *
 * Core tabs: Features (the feature atlas), Data (the panel as a chart or a table), Correlation
 * and IC, which show the snapshot's analysis lineage as an empty state. The earlier
 * `?tab=overview` and `?tab=analysis` links open Features and Data.
 * On asset panels an installed extension (`featureWorkspace` in `@/extensions`) may add tabs,
 * replace the Correlation and IC empty states with its own views, add header controls and mount
 * an overlay; without one the workspace shows the core tabs only.
 *
 * USAGE: <FeatureFamilyWorkspace path="1d/my/category/data.parquet" assetPanel />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ComponentType, Suspense } from 'react';
import { type FeatureWorkspaceProps, featureWorkspaceContribution } from '@/extensions';
import { useFeatureOverview } from '@/lib/api/feature-overview';
import { featureSetShape } from '@/lib/feature-set-tags';
import {
  Badge,
  EmptyState,
  ErrorPanel,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  PageHeader,
  ScrollArea,
  SegmentedControl,
  useSearchParamChoice,
} from '@/ui';
import { DatasetViewer } from './DatasetViewer';

// --------------------------------------------------------------------------- #
// Presentation
// --------------------------------------------------------------------------- #

// Core tabs with their slot order; extension tabs slot between them by their own `order`.
const CORE_MODES = [
  { value: 'features', label: 'Features', order: 10 },
  { value: 'data', label: 'Data', order: 30 },
  { value: 'correlation', label: 'Correlation', order: 50 },
  { value: 'ic', label: 'IC', order: 60 },
] as const;
const ANALYSIS_VIEWS = [
  { value: 'chart', label: 'Chart' },
  { value: 'table', label: 'Table' },
] as const;
const ANALYSIS_VIEW_VALUES = ANALYSIS_VIEWS.map((item) => item.value);
// Tab values from before the Features and Data renames, so old links land.
const RENAMED_MODES: Readonly<Record<string, string>> = {
  overview: 'features',
  analysis: 'data',
};
const contribution = featureWorkspaceContribution();

function ContributedView({
  component: View,
  path,
}: {
  component: ComponentType<FeatureWorkspaceProps>;
  path: string;
}) {
  return (
    <Suspense fallback={<LoadingSkeleton variant="table" label="Loading view" />}>
      <View path={path} />
    </Suspense>
  );
}

function AnalysisView({
  path,
  columns,
  preset,
  buildId,
}: {
  path: string;
  columns: string[];
  preset: string;
  buildId: string;
}) {
  const [view, setView] = useSearchParamChoice('view', ANALYSIS_VIEW_VALUES, 'chart');
  return (
    <DatasetViewer
      key={`${path}:${buildId}`}
      path={path}
      scope="features"
      compactChrome
      fill
      selectedColumns={columns}
      preset={preset}
      mode={view}
      hideModeControl
      toolbarLead={
        <SegmentedControl
          size="sm"
          className="shrink-0"
          ariaLabel="Analysis view"
          value={view}
          options={[...ANALYSIS_VIEWS]}
          onValueChange={setView}
        />
      }
    />
  );
}

// --------------------------------------------------------------------------- #
// Workspace
// --------------------------------------------------------------------------- #

export function FeatureFamilyWorkspace({
  path,
  label,
  description,
  sector,
  assetPanel = false,
}: {
  path: string;
  label?: string;
  description?: string;
  sector?: string | null;
  assetPanel?: boolean;
}) {
  const extra = assetPanel ? (contribution?.tabs ?? []) : [];
  const modes = [...CORE_MODES, ...extra]
    .sort((left, right) => left.order - right.order)
    .map(({ value, label }) => ({ value, label }));
  const [mode, setMode] = useSearchParamChoice(
    'tab',
    modes.map((item) => item.value),
    'features',
    { aliases: RENAMED_MODES },
  );
  const shape = featureSetShape(assetPanel);
  const metadataQuery = useFeatureOverview(path, { diagnostics: false });
  const data = metadataQuery.data;
  const icVerified = data?.analysis.ic === 'verified';
  const extraTab = extra.find((item) => item.value === mode);
  const upgrade =
    assetPanel && (mode === 'correlation' || mode === 'ic')
      ? contribution?.views?.[mode]
      : undefined;
  const upgradedView =
    upgrade && (!upgrade.requiresVerifiedIc || icVerified) ? upgrade.component : null;
  const HeaderControls = assetPanel && icVerified ? contribution?.headerControls : undefined;
  const Overlay = assetPanel && icVerified ? contribution?.overlay : undefined;
  const panel =
    data?.presets.find((item) => item.kind === 'full') ??
    data?.presets.find((item) => item.name === data.default_preset);
  const header = (
    <PageHeader
      title={label ?? data?.category ?? 'Features'}
      kicker={sector ?? undefined}
      badges={
        <span title={shape.title}>
          <Badge size="sm" tone={assetPanel ? 'info' : 'neutral'}>
            {shape.label}
          </Badge>
        </span>
      }
      subtitle={description}
      right={
        HeaderControls ? (
          <Suspense fallback={null}>
            <HeaderControls path={path} tab={mode} />
          </Suspense>
        ) : undefined
      }
      tabs={
        <SegmentedControl
          variant="tabs"
          ariaLabel="Feature view"
          value={mode}
          options={modes}
          onValueChange={setMode}
        />
      }
    />
  );
  const error = metadataQuery.error;
  return (
    <section
      aria-label="Feature family workspace"
      className="flex w-full min-h-0 min-w-0 flex-1 flex-col"
    >
      {header}
      {Overlay ? (
        <Suspense fallback={null}>
          <Overlay path={path} />
        </Suspense>
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {error && !data ? (
          <ErrorPanel message={error.message} onRetry={() => void metadataQuery.refetch()} />
        ) : isLoadingData(metadataQuery) ? (
          <LoadingSkeleton variant="table" label="Loading feature snapshot" />
        ) : !data || !panel ? (
          <EmptyState
            title="No feature panel in this snapshot"
            hint="The published snapshot has no full or default preset to show."
          />
        ) : extraTab ? (
          <ContributedView key={mode} component={extraTab.component} path={path} />
        ) : upgradedView ? (
          <ContributedView key={mode} component={upgradedView} path={path} />
        ) : mode === 'correlation' || mode === 'ic' ? (
          <ScrollArea axis="y" fill className="flex flex-col">
            <Inset padding="lg" className="flex flex-1 flex-col items-center justify-center">
              <EmptyState
                align="center"
                className="max-w-[65ch]"
                title={
                  data.analysis[mode === 'correlation' ? 'correlation' : 'ic'] === 'missing'
                    ? `${mode === 'correlation' ? 'Correlation' : 'IC'} not computed`
                    : data.analysis[mode === 'correlation' ? 'correlation' : 'ic'] === 'stale'
                      ? `${mode === 'correlation' ? 'Correlation' : 'IC'} was computed on an earlier snapshot`
                      : 'Analysis lineage is unverified'
                }
                hint={
                  mode !== 'correlation' && assetPanel
                    ? `No per-date cross-sectional IC has been published for snapshot ${data.build.id}.`
                    : `No verified results are available on snapshot ${data.build.id}. Existing analysis must identify its source build and selected columns before it can be shown here.`
                }
              />
            </Inset>
          </ScrollArea>
        ) : mode === 'data' ? (
          <AnalysisView
            path={path}
            columns={panel.columns}
            preset={panel.name}
            buildId={data.build.id}
          />
        ) : (
          <DatasetViewer
            key={`${path}:${data.build.id}`}
            path={path}
            scope="features"
            compactChrome
            fill
            selectedColumns={panel.columns}
            preset={panel.name}
            mode="features"
            hideModeControl
          />
        )}
      </div>
    </section>
  );
}
