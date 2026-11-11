/**
 * Read-only architecture map for the canonical data-to-decision pipeline.
 *
 * USAGE:
 *   <PipelineArchitectureMap />
 *   <PipelineArchitectureMap scope="platform" />
 *   <PipelineArchitectureMap scope="data" />
 *   <PipelineArchitectureMap scope="features" />
 *   <PipelineArchitectureMap
 *     scope="signals"
 *     laneRows={{ '01': { rows: signalRows, loading: query.isLoading, empty: 'no signal runs yet' } }}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn, lazyNamed } from '@quant-factory/qf-ui';
import { Suspense } from 'react';
import { Link } from 'react-router';
import { extensionPipelineRows } from '@/extensions';
import {
  type LogicalCatalogItem,
  useCatalogLabels,
  useFullLogicalCatalog,
} from '@/lib/api/catalog';

import './PipelineArchitectureMap.css';

// --------------------------------------------------------------------------- #
// Data
// --------------------------------------------------------------------------- #

export type PipelineArchitectureScope =
  | 'platform'
  | 'data'
  | 'features'
  | 'signals'
  | 'strategies'
  | 'research'
  | 'agents'
  | 'ml-engine';

export interface PipelineRow {
  key: string;
  detail: string;
  href?: string | null;
  /** DOM id for in-page anchors (section navigators link to `#id`). */
  id?: string;
}

/** Query-backed rows for one lane, keyed by lane index in `laneRows`. */
export interface PipelineLaneRows {
  rows: readonly PipelineRow[];
  loading?: boolean;
  empty?: string;
}

export interface PipelineArchitectureMapProps {
  scope?: PipelineArchitectureScope;
  laneRows?: Readonly<Record<string, PipelineLaneRows>>;
  hideHeader?: boolean;
  className?: string;
}

interface PipelineLane {
  index: string;
  label: string;
  description: string;
  path: string;
  href: string | null;
  rows: readonly PipelineRow[];
  /** Lake surface whose live catalog inventory fills this lane's rows. */
  source?: LakeSource;
}

/** Inventory lanes read from the logical catalog, never from hardcoded lists. */
type LakeSource = 'providers' | 'raw' | 'derived' | 'features';

const LAKE_EMPTY: Record<LakeSource, string> = {
  providers: 'no provider data landed yet',
  raw: 'no raw datasets yet',
  derived: 'no derived datasets yet',
  features: 'no feature sets built yet',
};

const STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Raw',
    description: 'Provider-shaped source truth',
    path: 'db/data/raw/',
    href: '/catalog?layer=raw',
    rows: [],
    source: 'raw',
  },
  {
    index: '02',
    label: 'Derived',
    description: 'Reusable same-day state',
    path: 'db/data/derived/',
    href: '/catalog?layer=derived',
    rows: [],
    source: 'derived',
  },
  {
    index: '03',
    label: 'Features',
    description: 'Point-in-time model inputs',
    path: 'db/features/',
    href: '/features',
    rows: [],
    source: 'features',
  },
  {
    index: '04',
    label: 'Signals',
    description: 'Research-ready observations',
    path: 'db/signals/',
    href: '/signals',
    rows: [],
  },
  {
    index: '05',
    label: 'Strategies',
    description: 'Versioned decision surfaces',
    path: 'db/strategies/',
    href: '/strategies',
    rows: [],
  },
];

const INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Provider feeds',
  description: 'Landed provider-shaped before any transformation',
  path: 'external',
  href: null,
  rows: [],
  source: 'providers',
};

const FEATURES_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Derived inputs',
  description: 'Same-day state the feature builders consume',
  path: 'db/data/derived/',
  href: '/catalog?layer=derived',
  rows: [],
  source: 'derived',
};

const FEATURES_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Feature sets',
    description: 'Point-in-time model inputs',
    path: 'db/features/',
    href: null,
    rows: [],
    source: 'features',
  },
  {
    index: '02',
    label: 'Analysis',
    description: 'Per-version feature diagnostics',
    path: 'db/features/_analysis/',
    href: null,
    rows: [
      { key: 'inventory', detail: 'columns · families · dtypes' },
      { key: 'quality', detail: 'coverage · nulls · stationarity' },
      { key: 'correlation', detail: 'pairs · clusters · duplicates' },
      { key: 'horizon ic', detail: 'IC matrix · walk-forward folds' },
    ],
  },
];

const SIGNALS_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Feature inputs',
  description: 'Point-in-time panels the signal models train on',
  path: 'db/features/',
  href: null,
  rows: [],
  source: 'features',
};

const SIGNALS_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Signal families',
    description: 'Research-ready observations',
    path: 'db/signals/',
    href: null,
    rows: [],
  },
  {
    index: '02',
    label: 'Runs',
    description: 'One model fit per run, never overwritten',
    path: 'db/signals/<family>/<run>/',
    href: null,
    rows: [
      { key: 'predictions', detail: 'per-date scores · targets · data range' },
      { key: 'metrics', detail: 'accuracy · AUC · cv metrics' },
      { key: 'metadata', detail: 'model type · params · feature list' },
    ],
  },
];

const STRATEGIES_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Signal inputs',
  description: 'Scored observations the strategies consume',
  path: 'db/signals/',
  href: null,
  rows: [],
};

const STRATEGIES_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Strategy types',
    description: 'Versioned decision surfaces',
    path: 'db/strategies/',
    href: null,
    rows: [],
  },
  {
    index: '02',
    label: 'Versions · runs',
    description: 'Immutable memory versions with their backtest runs',
    path: 'db/strategies/<type>/<vNNN>/',
    href: null,
    rows: [
      { key: 'version', detail: 'baseline · candidate · rejected · promoted' },
      { key: 'runs', detail: 'metrics · config · data range · preset leaders' },
      { key: 'surface', detail: 'research verdict · selected run · explicit promotion' },
    ],
  },
];

const RESEARCH_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Lake inputs',
  description: 'Canonical surfaces the sandbox reads from',
  path: 'db/',
  href: null,
  rows: [
    { key: 'db/data', detail: 'raw · derived', href: '/catalog' },
    { key: 'db/features', detail: 'point-in-time panels', href: '/features' },
    { key: 'db/signals', detail: 'scored runs', href: '/signals' },
    { key: 'package db/', detail: 'package-local lab data · not the shared lake' },
  ],
};

const RESEARCH_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Packages',
    description: 'Ad-hoc wired sandbox surfaces under Sandbox / Source',
    path: 'packages/research/',
    href: null,
    rows: [],
  },
  {
    index: '02',
    label: 'Surfaces · promotion',
    description: 'What a package exposes, and the only way out',
    path: 'packages/research/<package>/',
    href: null,
    rows: [
      { key: 'session', detail: 'composite bars · markers · selected run' },
      { key: 'lab_db', detail: 'package-local parquet files' },
      { key: 'promotion', detail: 'data → features → signals → strategies · never skip layers' },
    ],
  },
];

const AGENTS_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Operating inputs',
  description: 'Surfaces the loops read and write',
  path: 'db/ · packages/',
  href: null,
  rows: [
    { key: 'db/strategies', detail: 'versions · runs · surfaces', href: '/strategies' },
    { key: 'packages/research', detail: 'lab surfaces · promotion candidates', href: '/sandbox' },
  ],
};

const AGENTS_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Canonical agents',
    description: 'Runnable loop machinery and its readiness',
    path: 'agents/lib/',
    href: null,
    rows: [],
  },
  {
    index: '02',
    label: 'Loop machinery',
    description: 'What every canonical agent must ship',
    path: 'agents/lib/<agent>/',
    href: null,
    rows: [
      { key: 'program', detail: 'prompt steps · charter' },
      { key: 'driver', detail: 'runnable loop entry' },
      { key: 'tests', detail: 'readiness checks' },
    ],
  },
];

const ML_ENGINE_INPUT_LANE: PipelineLane = {
  index: 'IN',
  label: 'Training inputs',
  description: 'Consumer-owned data and explicit fit configuration',
  path: 'consumer → ml-engine',
  href: null,
  rows: [
    { key: 'matrices', detail: 'features · targets · optional weights' },
    { key: 'plan', detail: 'task · candidates · folds · metrics' },
    { key: 'final refit', detail: 'explicit true or false' },
  ],
};

const ML_ENGINE_STAGES: readonly PipelineLane[] = [
  {
    index: '01',
    label: 'Recent runs',
    description: 'Live progress and terminal training status',
    path: 'db/ml-engine/<run-id>.json',
    href: null,
    rows: [],
  },
  {
    index: '02',
    label: 'Readiness',
    description: 'Run inventory and optional inference artifacts',
    path: 'db/ml-engine/<run-id>/',
    href: null,
    rows: [],
  },
];

// --------------------------------------------------------------------------- #
// Lake inventory
// --------------------------------------------------------------------------- #

const unique = (values: readonly string[]) => [...new Set(values)].sort();

/** Items that have at least one landed parquet artifact. */
function landed(items: readonly LogicalCatalogItem[], layer: LogicalCatalogItem['layer']) {
  return items.filter((item) => item.layer === layer && item.resolutions.some((r) => r.exists));
}

function resolutionsOf(item: LogicalCatalogItem): string[] {
  return unique(item.resolutions.filter((r) => r.exists).map((r) => r.resolution));
}

/** Group a layer by resolution: `1d/` → the domains landed at that resolution. */
function byResolution(items: readonly LogicalCatalogItem[]): PipelineRow[] {
  const groups = new Map<string, string[]>();
  for (const item of items) {
    for (const resolution of resolutionsOf(item)) {
      groups.set(resolution, [
        ...(groups.get(resolution) ?? []),
        item.domain ?? item.category_path,
      ]);
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([resolution, domains]) => ({
      key: `${resolution}/`,
      detail: unique(domains).join(' · '),
    }));
}

function lakeRows(source: LakeSource, items: readonly LogicalCatalogItem[]): PipelineRow[] {
  switch (source) {
    case 'providers': {
      const raw = landed(items, 'raw');
      return unique(raw.map((item) => item.domain ?? item.category_path)).map((provider) => {
        const count = raw.filter((item) => (item.domain ?? item.category_path) === provider).length;
        return { key: provider, detail: `${count} dataset${count === 1 ? '' : 's'}` };
      });
    }
    case 'raw':
      return byResolution(landed(items, 'raw'));
    case 'derived':
      return byResolution(landed(items, 'derived'));
    case 'features':
      return landed(items, 'features').map((item) => ({
        key: item.category_path,
        detail: `${item.label} — ${resolutionsOf(item).join(' · ')}`,
        href: `/features?item=${encodeURIComponent(item.id)}`,
      }));
  }
}

/** Live rows for every catalog-backed lane; caller-supplied `laneRows` still win. */
function useLakeLaneRows(lanes: readonly PipelineLane[]): Record<string, PipelineLaneRows> {
  const needed = lanes.some((lane) => lane.source);
  const query = useFullLogicalCatalog({}, needed);
  const items = query.data?.items ?? [];
  const result: Record<string, PipelineLaneRows> = {};
  for (const lane of lanes) {
    if (!lane.source) continue;
    result[lane.index] = {
      rows: query.data ? lakeRows(lane.source, items) : [],
      loading: query.isLoading,
      empty: query.error ? 'catalog unavailable' : LAKE_EMPTY[lane.source],
    };
  }
  return result;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

interface LaneProps {
  lane: PipelineLane;
  arrow: boolean;
  override?: PipelineLaneRows;
}

function LaneRows({ lane, override }: Pick<LaneProps, 'lane' | 'override'>) {
  const { data: labels = {} } = useCatalogLabels();
  // Replace complete prose tokens only; slugs inside paths and URLs stay literal.
  const display = (text: string) =>
    text
      .split(/(\s+|[·—])/)
      .map((part) => (part.includes('/') || !Object.hasOwn(labels, part) ? part : labels[part]))
      .join('');
  const rows = override?.rows ?? lane.rows;
  if (override?.loading) {
    return (
      <ul
        className="pipeline-rows motion-safe:animate-pulse"
        role="status"
        aria-label="Loading rows"
      >
        {[0, 1, 2, 3].map((item) => (
          <li key={item}>
            <span className="pipeline-row-key">
              <span className="pipeline-row-bar" />
            </span>
            <span className="pipeline-row-detail">
              <span className="pipeline-row-bar is-detail" />
            </span>
          </li>
        ))}
      </ul>
    );
  }
  if (!rows.length) {
    return override?.empty ? <p className="pipeline-lane-empty">{override.empty}</p> : null;
  }
  return (
    <ul className="pipeline-rows">
      {rows.map((row) => (
        <li key={row.key} id={row.id} className={row.href ? 'pipeline-row--link' : undefined}>
          {row.href ? (
            <Link className="pipeline-row-link" to={row.href}>
              <span className="pipeline-row-key" data-identifier>
                {display(row.key)}
              </span>
              <span className="pipeline-row-detail">{display(row.detail)}</span>
            </Link>
          ) : (
            <>
              <span className="pipeline-row-key" data-identifier>
                {display(row.key)}
              </span>
              <span className="pipeline-row-detail">{display(row.detail)}</span>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function LaneBody({ lane, arrow, override }: LaneProps) {
  return (
    <>
      <div className="pipeline-lane-head">
        <span className="pipeline-lane-eyebrow">
          {arrow ? <span className="pipeline-lane-arrow">→</span> : null}
          {lane.index}
        </span>
        <strong>{lane.label}</strong>
        <span className="pipeline-lane-description">{lane.description}</span>
        <code>{lane.path}</code>
      </div>
      <LaneRows lane={lane} override={override} />
    </>
  );
}

const PipelineLaneCopy = lazyNamed(() => import('./PipelineLaneCopy'), 'PipelineLaneCopy');

/** True for a literal repo or lake path; labels and `<placeholder>` templates are not copyable. */
function isCopyablePath(path: string): boolean {
  return /^[\w./-]+$/.test(path) && path.includes('/');
}

function Lane({ lane, arrow, override }: LaneProps) {
  const body = <LaneBody lane={lane} arrow={arrow} override={override} />;
  return (
    <div className="pipeline-lane-cell">
      {lane.href ? (
        <Link className="pipeline-lane pipeline-lane--link" to={lane.href}>
          {body}
        </Link>
      ) : (
        <div className="pipeline-lane">{body}</div>
      )}
      {/* A sibling of the card link: a button may not nest inside an anchor. */}
      {isCopyablePath(lane.path) ? (
        <Suspense fallback={null}>
          <PipelineLaneCopy path={lane.path} />
        </Suspense>
      ) : null}
    </div>
  );
}

interface PipelineScopeConfig {
  lanes: readonly PipelineLane[];
  title: string;
  path: string;
  contract: string;
  heading: 'h1' | 'h2';
  control: string;
  read: string;
  strip: string;
}

const SCOPES: Record<PipelineArchitectureScope, PipelineScopeConfig> = {
  platform: {
    lanes: [INPUT_LANE, ...STAGES],
    title: 'Platform pipeline',
    path: 'db',
    contract: 'data → features → signals → strategies',
    heading: 'h2',
    control: 'sync · materialize · validate',
    read: 'catalog · preview · chart',
    strip: 'point-in-time rows · canonical parquet · read-only query surface',
  },
  data: {
    lanes: [INPUT_LANE, ...STAGES.slice(0, 2)],
    title: 'Data',
    path: 'db/data',
    contract: 'provider → raw → derived',
    heading: 'h1',
    control: 'sync · materialize · validate',
    read: 'catalog · preview · chart',
    strip: 'point-in-time rows · canonical parquet · read-only query surface',
  },
  features: {
    lanes: [FEATURES_INPUT_LANE, ...FEATURES_STAGES],
    title: 'Features',
    path: 'db/features',
    contract: 'derived → features → signals',
    heading: 'h1',
    control: 'build · version · register',
    read: 'table · chart · correlation · ic matrix',
    strip: 'point-in-time rows · versioned parquet · REGISTRY.yaml',
  },
  signals: {
    lanes: [SIGNALS_INPUT_LANE, ...SIGNALS_STAGES],
    title: 'Signals',
    path: 'db/signals',
    contract: 'features → signals → strategies',
    heading: 'h1',
    control: 'train · score · register',
    read: 'runs · predictions · metrics',
    strip: 'one run per fit · predictions parquet · run metadata',
  },
  strategies: {
    lanes: [STRATEGIES_INPUT_LANE, ...STRATEGIES_STAGES],
    title: 'Strategies',
    path: 'db/strategies',
    contract: 'signals → strategies → execution',
    heading: 'h1',
    control: 'backtest · version · promote',
    read: 'versions · runs · surfaces',
    strip: 'immutable memory versions · backtest runs · explicit promotion',
  },
  research: {
    lanes: [RESEARCH_INPUT_LANE, ...RESEARCH_STAGES],
    title: 'Sandbox',
    path: 'packages/research/sandbox',
    contract: 'sandbox → promotion',
    heading: 'h1',
    control: 'prototype · record · promote',
    read: 'sessions · markers · package db',
    strip: 'ad-hoc sandbox surfaces · not production strategies · explicit promotion',
  },
  agents: {
    lanes: [AGENTS_INPUT_LANE, ...AGENTS_STAGES],
    title: 'Agents',
    path: 'agents',
    contract: 'charter → loop → version',
    heading: 'h1',
    control: 'charter · run · record',
    read: 'inventory · readiness · steps',
    strip: 'canonical runnable loops · program · driver · tests',
  },
  'ml-engine': {
    lanes: [ML_ENGINE_INPUT_LANE, ...ML_ENGINE_STAGES],
    title: 'ML Engine',
    path: 'db/ml-engine',
    contract: 'fit → evaluate → artifact',
    heading: 'h1',
    control: 'train · evaluate · save',
    read: 'runs · progress · results',
    strip:
      'atomic JSON sidecar · optional immutable TrainingResult artifact · read-only observability',
  },
};

export function PipelineArchitectureMap({
  scope = 'platform',
  laneRows,
  hideHeader = false,
  className,
}: PipelineArchitectureMapProps) {
  const { lanes, title, path, contract, heading, control, read, strip } = SCOPES[scope];
  const Heading = heading;
  const lakeLaneRows = useLakeLaneRows(lanes);
  const resolvedLanes = lanes.map((lane) => ({
    ...lane,
    rows: [...lane.rows, ...extensionPipelineRows(scope, lane.index)],
  }));

  return (
    <section
      className={cn(`pipeline-architecture-map pipeline-architecture-map--${scope}`, className)}
      aria-label={hideHeader ? title : undefined}
      aria-labelledby={hideHeader ? undefined : 'pipeline-architecture-title'}
    >
      {hideHeader ? null : (
        <header className="pipeline-architecture-header">
          <div className="pipeline-architecture-title">
            <Heading id="pipeline-architecture-title">{title}</Heading>
            <code>{path}</code>
          </div>
          <code className="pipeline-architecture-contract">{contract}</code>
        </header>
      )}

      <div className={`pipeline-lanes pipeline-lanes--${resolvedLanes.length}`}>
        {resolvedLanes.map((lane, index) => (
          <Lane
            key={lane.label}
            lane={lane}
            arrow={index > 0}
            override={laneRows?.[lane.index] ?? lakeLaneRows[lane.index]}
          />
        ))}
      </div>

      <footer className="pipeline-strip">
        <span className="pipeline-strip-cell">
          <span className="pipeline-strip-key">Control</span>
          <span>{control}</span>
        </span>
        <span className="pipeline-strip-cell">
          <span className="pipeline-strip-key">Read</span>
          <span>{read}</span>
        </span>
        <span className="pipeline-strip-cell pipeline-strip-cell--contract">{strip}</span>
      </footer>
    </section>
  );
}
