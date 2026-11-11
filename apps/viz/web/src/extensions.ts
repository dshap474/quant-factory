/**
 * Typed build-time registry for optional Viz extensions.
 *
 * USAGE:
 *   extensionRoutes('dashboards');
 *   dashboardNavigation();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentType, LazyExoticComponent } from 'react';
import type { SignalData, SignalResearchVersion } from '@/lib/api/signals';
import type { PipelineArchitectureScope, PipelineRow } from '@/ui';

// --------------------------------------------------------------------------- #
// Contracts
// --------------------------------------------------------------------------- #

export type ExtensionMount = 'dashboards' | 'sandbox' | 'strategies' | 'signals' | 'execution';

export interface ExtensionRoute {
  path: string;
  component: LazyExoticComponent<ComponentType>;
  order: number;
}

export interface ExtensionNavigation {
  label: string;
  path: string;
  position: number;
}

export interface ResearchCatalogItem {
  id: string;
  route: string;
  nav_path?: string[];
  surface?: string;
  file_count?: number;
  db_available?: boolean;
  session_kind?: string;
  session_count?: number;
  composite_available?: boolean;
  selected_run?: { run_id: string } | null;
}

export interface SignalRunPanelProps {
  signalData: SignalData;
  chartData: Array<{ date: Date; value: number }>;
  label: string;
}

export interface SignalVersionPanelProps {
  family: string;
  memoryVersion: string;
  isCanonical: boolean;
  version: SignalResearchVersion;
}

export interface StrategyTradePanelProps {
  strategyType: string;
  memoryVersion: string;
}

/** Rendered below the generic Composition surface; owns its own run-bound reads. */
export interface StrategyCompositionPanelProps {
  strategyType: string;
  memoryVersion: string;
  selectedRunId: string | null;
}

/** Where an Ops panel is rendered: `scope` is a package name (`data`, `features`, …) or a page id. */
export interface OpsPanelProps {
  scope: string;
}

/**
 * One panel of the Ops page. A package panel shows on the Runs page (`/ops/runs`, every package with
 * scope `''`; `/ops/runs/<package>`, one), stacked by `order`. A panel with a `page` is instead a
 * navigator page of its own (`/ops/<page.id>`), listed after Runs, for work that belongs to no one
 * package. A `home` panel renders on the Ops home page.
 */
export interface OpsPanel {
  id: string;
  order: number;
  page?: { id: string; label: string };
  /** Shown on the Ops home page (`/ops`, reached from the navigator title) instead of a package page. */
  home?: boolean;
  /** The panel's id and label (shown when it is the Ops home or a page). */
  view: { id: string; label: string };
  /** Packages whose Runs tabs show this panel (the All tab shows it too); default every package. */
  scopes?: readonly string[];
  component: LazyExoticComponent<ComponentType<OpsPanelProps>>;
}

/** What every feature-workspace contribution receives: the published snapshot path. */
export interface FeatureWorkspaceProps {
  path: string;
}

/** Header controls also receive the active workspace tab, so they can show per-tab controls. */
export interface FeatureWorkspaceHeaderProps extends FeatureWorkspaceProps {
  tab: string;
}

/**
 * Asset-panel additions to the feature family workspace (one owner). Core tabs are Features (10),
 * Data (30), Correlation (50) and IC (60); extra `tabs` slot in by `order` and may not reuse a
 * core tab value. `views` replace a core analysis tab's empty state; `headerControls` and `overlay` render only when the snapshot's IC
 * lineage is verified, as do `views` with `requiresVerifiedIc`.
 */
export interface FeatureWorkspaceContribution {
  tabs?: readonly {
    value: string;
    label: string;
    order: number;
    component: LazyExoticComponent<ComponentType<FeatureWorkspaceProps>>;
  }[];
  views?: Partial<
    Record<
      'correlation' | 'ic',
      {
        component: LazyExoticComponent<ComponentType<FeatureWorkspaceProps>>;
        requiresVerifiedIc?: boolean;
      }
    >
  >;
  headerControls?: LazyExoticComponent<ComponentType<FeatureWorkspaceHeaderProps>>;
  overlay?: LazyExoticComponent<ComponentType<FeatureWorkspaceProps>>;
}

/** The Execution section's navigator and index page, rendered by its core layout (one owner). */
export interface SectionContribution {
  navigator?: LazyExoticComponent<ComponentType>;
  index?: LazyExoticComponent<ComponentType>;
}

export interface StrategyCurrentDataReplay {
  sourceVersion: string;
  sourceSeries: 'strategy' | 'benchmark';
  label: string;
}

/** One extra research-comparison metric row, resolved from the strategy and comparison columns' metrics objects; the benchmark column shows no value. */
export interface StrategyExtraMetric {
  key: string;
  label: string;
  /** Read or derive the value from one column's metrics (unknown published fields included). */
  resolve: (metrics: Readonly<Record<string, unknown>>) => number | null;
  format?: 'number' | 'percent';
  higherIsBetter?: boolean;
}

export interface VizExtension {
  id: string;
  mount: ExtensionMount;
  order: number;
  routes?: readonly ExtensionRoute[];
  navigation?: readonly ExtensionNavigation[];
  defaultDashboard?: string;
  strategyRows?: readonly PipelineRow[];
  strategyRedirects?: Readonly<Record<string, string>>;
  invalidationLinks?: Readonly<Record<string, { to: string; label: string }>>;
  strategyPresentation?: {
    strategyType: string;
    /** Extra rows appended to the research performance comparison table. */
    extraMetrics?: readonly StrategyExtraMetric[];
    /** Hide the separate buy-and-hold benchmark overlay on research charts. */
    suppressBenchmarkOverlay?: boolean;
    /** Benchmark ticker (`/api/benchmarks/{ticker}`) overlaid on every Backtesting chart and preferred as the research charts' buy-and-hold overlay. */
    backtestBenchmark?: string;
    currentDataReplays?: Readonly<Record<string, StrategyCurrentDataReplay>>;
    /** Per version, the one cost (bps) whose optimizer-grid curves are charted. */
    gridCurveCostBps?: Readonly<Record<string, number>>;
  };
  researchPackageSummary?: {
    route: string;
    describe: (item: ResearchCatalogItem) => string;
  };
  signalRunPanels?: readonly {
    signalType: string;
    component: LazyExoticComponent<ComponentType<SignalRunPanelProps>>;
  }[];
  signalVersionPanels?: readonly {
    family: string;
    versions: readonly string[];
    component: LazyExoticComponent<ComponentType<SignalVersionPanelProps>>;
  }[];
  strategyTradePanels?: readonly {
    strategyType: string;
    versions: readonly string[];
    component: LazyExoticComponent<ComponentType<StrategyTradePanelProps>>;
  }[];
  strategyCompositionPanels?: readonly {
    strategyType: string;
    versions: readonly string[];
    component: LazyExoticComponent<ComponentType<StrategyCompositionPanelProps>>;
  }[];
  opsPanels?: readonly OpsPanel[];
  /** Extra tabs, upgraded views, header controls and an overlay for asset-panel feature workspaces. */
  featureWorkspace?: FeatureWorkspaceContribution;
  /** The navigator and index page of the Execution section (only `mount: 'execution'` may set it). */
  section?: SectionContribution;
  pipelineRows?: Partial<
    Record<PipelineArchitectureScope, Readonly<Record<string, readonly PipelineRow[]>>>
  >;
}

// --------------------------------------------------------------------------- #
// Validation
// --------------------------------------------------------------------------- #

const PUBLIC_ROUTES = new Set([
  'sandbox/doc/*',
  'strategies/:type',
  'strategies/:type/:memoryVersion',
  'signals/:family',
  'signals/:family/:memoryVersion',
]);

function fullRoute(mount: ExtensionMount, path: string): string {
  return `${mount}/${path}`;
}

function parameterRouteShadows(earlier: string, later: string): boolean {
  const left = earlier.split('/');
  const right = later.split('/');
  return (
    left.length === right.length &&
    left.some((part) => part.startsWith(':')) &&
    left.every((part, index) => part.startsWith(':') || part === right[index])
  );
}

export function validateExtensions(extensions: readonly VizExtension[]): void {
  const ids = new Set<string>();
  const routes = new Set<string>();
  const navPositions = new Set<string>();
  const defaultDashboards = new Set<string>();
  const strategyRedirects = new Set<string>();
  const invalidationLinks = new Set<string>();
  const strategyPresentations = new Set<string>();
  const researchSummaries = new Set<string>();
  const signalRunPanels = new Set<string>();
  const signalVersionPanels = new Set<string>();
  const strategyTradePanels = new Set<string>();
  const strategyCompositionPanels = new Set<string>();
  const opsPanelIds = new Set<string>();
  const featureWorkspaces = new Set<string>();
  const sections = new Set<string>();

  function claim(claims: Set<string>, key: string, label: string): void {
    if (claims.has(key)) throw new Error(`Duplicate ${label}: ${key}`);
    claims.add(key);
  }

  for (const extension of extensions) {
    if (ids.has(extension.id)) throw new Error(`Duplicate extension ID: ${extension.id}`);
    ids.add(extension.id);

    const declaredRoutes = extension.routes ?? [];
    for (const [index, route] of declaredRoutes.entries()) {
      const routeKey = fullRoute(extension.mount, route.path);
      if (PUBLIC_ROUTES.has(routeKey))
        throw new Error(`Extension route shadows public route: ${routeKey}`);
      if (routes.has(routeKey)) throw new Error(`Duplicate extension route: ${routeKey}`);
      routes.add(routeKey);
      for (const later of declaredRoutes.slice(index + 1)) {
        if (parameterRouteShadows(route.path, later.path)) {
          throw new Error(
            `Parameter route ${routeKey} appears before ${fullRoute(extension.mount, later.path)}`,
          );
        }
      }
    }

    for (const item of extension.navigation ?? []) {
      const positionKey = `${extension.mount}:${item.position}`;
      if (navPositions.has(positionKey))
        throw new Error(`Duplicate navigation position: ${positionKey}`);
      navPositions.add(positionKey);
      if (!routes.has(item.path.replace(/^\//, ''))) {
        throw new Error(`Navigation points to an unregistered extension route: ${item.path}`);
      }
    }

    if (extension.defaultDashboard) {
      claim(defaultDashboards, 'default', 'default dashboard owner');
    }
    for (const key of Object.keys(extension.strategyRedirects ?? {})) {
      claim(strategyRedirects, key, 'strategy redirect');
    }
    for (const key of Object.keys(extension.invalidationLinks ?? {})) {
      claim(invalidationLinks, key, 'invalidation link');
    }
    if (extension.strategyPresentation) {
      claim(
        strategyPresentations,
        extension.strategyPresentation.strategyType,
        'strategy presentation',
      );
    }
    if (extension.researchPackageSummary) {
      claim(researchSummaries, extension.researchPackageSummary.route, 'research summary route');
    }
    for (const panel of extension.signalRunPanels ?? []) {
      claim(signalRunPanels, panel.signalType, 'signal run panel');
    }
    for (const panel of extension.opsPanels ?? []) {
      claim(opsPanelIds, panel.id, 'ops panel');
    }
    if (extension.featureWorkspace) {
      claim(featureWorkspaces, 'owner', 'feature workspace owner');
      const featureTabs = new Set<string>(['features', 'data', 'correlation', 'ic']);
      for (const tab of extension.featureWorkspace.tabs ?? [])
        claim(featureTabs, tab.value, 'feature workspace tab');
    }
    if (extension.section) {
      if (extension.mount !== 'execution')
        throw new Error(`Section contribution needs mount 'execution': ${extension.id}`);
      claim(sections, extension.mount, 'section owner');
    }
    for (const panel of extension.strategyTradePanels ?? []) {
      for (const version of panel.versions)
        claim(strategyTradePanels, `${panel.strategyType}/${version}`, 'strategy trade panel');
    }
    for (const panel of extension.strategyCompositionPanels ?? []) {
      for (const version of panel.versions)
        claim(
          strategyCompositionPanels,
          `${panel.strategyType}/${version}`,
          'strategy composition panel',
        );
    }
    for (const panel of extension.signalVersionPanels ?? []) {
      for (const version of panel.versions) {
        claim(signalVersionPanels, `${panel.family}/${version}`, 'signal version panel');
      }
    }
  }
}

// --------------------------------------------------------------------------- #
// Build-time discovery
// --------------------------------------------------------------------------- #

const extensionModules = import.meta.glob<{ default: VizExtension }>(
  '../../extensions/*/extension.tsx',
  { eager: true },
);

export const extensions = Object.entries(extensionModules)
  .sort(([left], [right]) => left.localeCompare(right))
  .map(([, module]) => module.default);

validateExtensions(extensions);

// --------------------------------------------------------------------------- #
// Consumers
// --------------------------------------------------------------------------- #

export function extensionRoutes(mount: ExtensionMount): ExtensionRoute[] {
  return extensions
    .filter((extension) => extension.mount === mount)
    .flatMap((extension) => extension.routes ?? [])
    .sort((left, right) => left.order - right.order || left.path.localeCompare(right.path));
}

export function dashboardNavigation(): ExtensionNavigation[] {
  return extensions
    .filter((extension) => extension.mount === 'dashboards')
    .flatMap((extension) => extension.navigation ?? [])
    .sort((left, right) => left.position - right.position);
}

/** Execution-mount navigation entries, for the extension that owns the Execution `section` to render. */
export function executionNavigation(): ExtensionNavigation[] {
  return extensions
    .filter((extension) => extension.mount === 'execution')
    .flatMap((extension) => extension.navigation ?? [])
    .sort((left, right) => left.position - right.position);
}

/** True when an installed extension mounts this section; extension-only sections hide otherwise. */
export function mountInstalled(mount: ExtensionMount): boolean {
  return extensions.some((extension) => extension.mount === mount);
}

/** The installed navigator and index page for a section, or null when no extension contributes one. */
export function sectionContribution(mount: ExtensionMount): SectionContribution | null {
  return (
    extensions.find((extension) => extension.mount === mount && extension.section)?.section ?? null
  );
}

/** Every dashboard the Dashboards navigator and the command menu list, in display order. */
export function dashboardDestinations(): ExtensionNavigation[] {
  return dashboardNavigation();
}

export function defaultDashboard(): string | null {
  return (
    extensions
      .filter((extension) => extension.defaultDashboard)
      .sort((left, right) => left.order - right.order)[0]?.defaultDashboard ?? null
  );
}

/** The installed feature-workspace contribution, or null when none is installed. */
export function featureWorkspaceContribution(): FeatureWorkspaceContribution | null {
  return extensions.find((extension) => extension.featureWorkspace)?.featureWorkspace ?? null;
}

/** Ops page sections from installed extensions; the Ops tab is hidden when there are none. */
export function opsPanels(): OpsPanel[] {
  return extensions
    .flatMap((extension) => extension.opsPanels ?? [])
    .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));
}

export function extensionStrategyRows(): readonly PipelineRow[] {
  return extensions.flatMap((extension) => extension.strategyRows ?? []);
}

export function strategyRedirect(strategyType: string, memoryVersion: string): string | null {
  const key = `${strategyType}/${memoryVersion}`;
  return extensions.map((extension) => extension.strategyRedirects?.[key]).find(Boolean) ?? null;
}

export function invalidationLink(strategyType: string, memoryVersion: string) {
  const key = `${strategyType}/${memoryVersion}`;
  return extensions.map((extension) => extension.invalidationLinks?.[key]).find(Boolean) ?? null;
}

export function strategyExtraMetrics(strategyType: string): readonly StrategyExtraMetric[] {
  const owner = extensions.find(
    (extension) => extension.strategyPresentation?.strategyType === strategyType,
  );
  return owner?.strategyPresentation?.extraMetrics ?? [];
}

export function strategySuppressesBenchmarkOverlay(strategyType: string): boolean {
  return extensions.some(
    (extension) =>
      extension.strategyPresentation?.strategyType === strategyType &&
      extension.strategyPresentation.suppressBenchmarkOverlay,
  );
}

export function strategyBacktestBenchmark(strategyType: string): string | null {
  const owner = extensions.find(
    (extension) => extension.strategyPresentation?.strategyType === strategyType,
  );
  return owner?.strategyPresentation?.backtestBenchmark ?? null;
}

export function strategyCurrentDataReplay(
  strategyType: string,
  memoryVersion: string,
): StrategyCurrentDataReplay | null {
  const owner = extensions.find(
    (extension) => extension.strategyPresentation?.strategyType === strategyType,
  );
  return owner?.strategyPresentation?.currentDataReplays?.[memoryVersion] ?? null;
}

export function strategyGridCurveCostBps(
  strategyType: string,
  memoryVersion: string,
): number | null {
  const owner = extensions.find(
    (extension) => extension.strategyPresentation?.strategyType === strategyType,
  );
  return owner?.strategyPresentation?.gridCurveCostBps?.[memoryVersion] ?? null;
}

export function researchPackageDetail(item: ResearchCatalogItem): string {
  const owner = extensions.find(
    (extension) => extension.researchPackageSummary?.route === item.route,
  );
  return (
    owner?.researchPackageSummary?.describe(item) ??
    ((item.nav_path ?? []).join(' / ') || 'Research')
  );
}

export function signalRunPanel(signalType: string) {
  return extensions
    .flatMap((extension) => extension.signalRunPanels ?? [])
    .find((panel) => panel.signalType === signalType);
}

export function signalVersionPanel(family: string, memoryVersion: string) {
  return extensions
    .flatMap((extension) => extension.signalVersionPanels ?? [])
    .find((panel) => panel.family === family && panel.versions.includes(memoryVersion));
}

export function strategyTradePanel(strategyType: string, memoryVersion: string) {
  return extensions
    .flatMap((extension) => extension.strategyTradePanels ?? [])
    .find((panel) => panel.strategyType === strategyType && panel.versions.includes(memoryVersion));
}

export function strategyCompositionPanel(strategyType: string, memoryVersion: string) {
  return extensions
    .flatMap((extension) => extension.strategyCompositionPanels ?? [])
    .find((panel) => panel.strategyType === strategyType && panel.versions.includes(memoryVersion));
}

export function extensionPipelineRows(
  scope: PipelineArchitectureScope,
  lane: string,
): readonly PipelineRow[] {
  return extensions.flatMap((extension) => extension.pipelineRows?.[scope]?.[lane] ?? []);
}
