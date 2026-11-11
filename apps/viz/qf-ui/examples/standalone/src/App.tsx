/**
 * The one page of the qf-ui standalone example: the app shell (primary rail, a section
 * navigator with search and a selected row, the section workspace), a PageShell with a
 * segmented control, a line chart, a price/profile chart, a paged DataTable with declarative
 * cell kinds (identifier, status, number, percent, count), a heat DataTable, and formatter
 * output. All data is fake and deterministic.
 *
 * USAGE:
 *   <QfRouterProvider adapter={historyAdapter}><App /></QfRouterProvider>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  DataList,
  formatCompact,
  formatCount,
  formatMoney,
  formatPercent,
  formatSignedPercent,
  ICON_SIZE,
  ICON_STROKE,
  Navigator,
  type NavigatorNode,
  PageHeader,
  PageShell,
  RailNavLink,
  RailNavList,
  Section,
  SectionWorkspace,
  SegmentedControl,
  SidebarShell,
  truncateMiddle,
} from '@quant-factory/qf-ui';
import {
  type MultiSeriesSourceSeries,
  MultiSeriesTimeChart,
  PriceProfileChart,
} from '@quant-factory/qf-ui/charts/renderers';
import { chartColor } from '@quant-factory/qf-ui/charts/theme';
import { DataTable, type DataTableColumn } from '@quant-factory/qf-ui/tables';
import { ChartLine, Database, FlaskConical } from 'lucide-react';
import { useMemo, useState } from 'react';

import { usePathname } from './router';

// --------------------------------------------------------------------------- #
// Fake data
// --------------------------------------------------------------------------- #

const DAY_MS = 86_400_000;
const START = Date.UTC(2026, 0, 1);

/** Deterministic pseudo-random walk so builds and screenshots are stable. */
function walk(seed: number, length: number, start: number, step: number): number[] {
  let state = seed;
  let value = start;
  const out: number[] = [];
  for (let i = 0; i < length; i += 1) {
    state = (state * 16807) % 2147483647;
    value *= 1 + (state / 2147483647 - 0.48) * step;
    out.push(value);
  }
  return out;
}

const LINE_SERIES: MultiSeriesSourceSeries[] = [
  { metric: 'strategy', label: 'Strategy', seed: 7 },
  { metric: 'control', label: 'Control', seed: 11 },
  { metric: 'hedge', label: 'Hedge', seed: 23 },
].map(({ metric, label, seed }) => ({
  metric,
  label,
  axis: 'left',
  points: walk(seed, 240, 100, 0.03).map((y, i) => ({ x: new Date(START + i * DAY_MS), y })),
}));

const SESSION_OPEN = Date.UTC(2026, 9, 5, 0);
const MINUTE_MS = 60_000;
const SESSION_PRICES = walk(3, 24 * 12, 62_000, 0.004);
const SESSION_POINTS = SESSION_PRICES.map(
  (price, i) => [SESSION_OPEN + i * 5 * MINUTE_MS, price] as const,
);
const SESSION_CLOSE = SESSION_OPEN + 24 * 60 * MINUTE_MS;
const PROFILE_ROWS = (() => {
  const counts = new Map<number, number>();
  for (const price of SESSION_PRICES) {
    const row = Math.round(price / 100) * 100;
    counts.set(row, (counts.get(row) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => a[0] - b[0]);
})();
const PROFILE_PRICES = PROFILE_ROWS.map(([price]) => price);
const VALUE_BAND = [
  PROFILE_PRICES[Math.floor(PROFILE_PRICES.length * 0.3)] ?? 0,
  PROFILE_PRICES[Math.floor(PROFILE_PRICES.length * 0.7)] ?? 0,
] as const;

const TABLE_ROWS = Array.from({ length: 23 }, (_, i) => ({
  run_id: `run-2026100${i % 9}-${(i * 7919).toString(16).padStart(6, '0')}abcdef`,
  sharpe: Number((((i * 37) % 23) / 10 - 0.8).toFixed(2)),
  cagr: Number((((i * 53) % 41) / 100 - 0.12).toFixed(3)),
  trades: 120 + ((i * 97) % 400),
  status: ['completed', 'running', 'failed'][i % 3] ?? 'completed',
}));

const HEAT_ROWS = [
  { asset: 'BTC', address: '0x8f3a9b2c4d5e6f708192a3b4c5d6e7f8091a2b3c', ic: 0.084 },
  { asset: 'ETH', address: '0x1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e', ic: -0.031 },
  { asset: 'SOL', address: '0x9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d', ic: 0.012 },
  { asset: 'DOGE', address: '0x00aa11bb22cc33dd44ee55ff66778899aabbccdd', ic: -0.067 },
];
const HEAT_MAX = 0.084;

type View = 'overview' | 'tables';

const VIEW_OPTIONS = [
  { value: 'overview' as const, label: 'Overview' },
  { value: 'tables' as const, label: 'Tables' },
];

// --------------------------------------------------------------------------- #
// Shell pieces
// --------------------------------------------------------------------------- #

const RAIL_ITEMS = [
  { label: 'Data', href: '/data', icon: Database },
  { label: 'Strategies', href: '/', icon: ChartLine },
  { label: 'Research', href: '/research', icon: FlaskConical },
];

function PrimaryRail({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = usePathname();
  return (
    <SidebarShell
      title="qf-ui example"
      brandShort="qf"
      href="/"
      rail
      collapsed={collapsed}
      onToggleCollapse={onToggle}
    >
      <RailNavList aria-label="Main navigation">
        {RAIL_ITEMS.map(({ label, href, icon: Icon }) => (
          <RailNavLink
            key={href}
            to={href}
            label={label}
            collapsed={collapsed}
            current={href === '/' ? pathname === '/' : pathname.startsWith(href)}
            icon={<Icon size={ICON_SIZE} strokeWidth={ICON_STROKE} />}
          />
        ))}
      </RailNavList>
    </SidebarShell>
  );
}

const STRATEGIES = ['breakout-follower', 'mean-reversion', 'carry-basket'];

function StrategyNavigator() {
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ 'breakout-follower': true });
  const items = useMemo<NavigatorNode[]>(
    () =>
      STRATEGIES.filter((name) => name.includes(query.trim().toLowerCase())).map((name) => ({
        id: name,
        label: name,
        expanded: expanded[name] ?? false,
        onToggle: () => setExpanded((state) => ({ ...state, [name]: !state[name] })),
        children: ['v011', 'v010', 'v009'].map((version, index) => ({
          id: `${name}/${version}`,
          label: version,
          to: `/?strategy=${name}&version=${version}`,
          current: name === 'breakout-follower' && index === 0,
          ...(index === 0 ? { tag: { label: 'candidate', tone: 'success' as const } } : {}),
        })),
      })),
    [expanded, query],
  );
  return (
    <Navigator
      title="Strategies"
      listLabel="Strategy hierarchy"
      search={{
        id: 'strategy-search',
        label: 'Search strategies',
        placeholder: 'Search strategies',
        value: query,
        onChange: setQuery,
      }}
      empty={`No strategies match “${query}”.`}
      items={items}
    />
  );
}

// --------------------------------------------------------------------------- #
// Page
// --------------------------------------------------------------------------- #

function FormatterList() {
  return (
    <DataList
      items={[
        { label: 'formatPercent(0.1234)', value: formatPercent(0.1234) },
        { label: 'formatSignedPercent(0.042)', value: formatSignedPercent(0.042) },
        { label: 'formatMoney(1234.5)', value: formatMoney(1234.5) },
        { label: 'formatCount(1234567)', value: formatCount(1234567) },
        { label: 'formatCompact(2.5e9)', value: formatCompact(2.5e9) },
        { label: 'truncateMiddle(address)', value: truncateMiddle(HEAT_ROWS[0]?.address ?? '') },
      ]}
    />
  );
}

const RUN_COLUMNS: DataTableColumn<(typeof TABLE_ROWS)[number]>[] = [
  { key: 'run_id', header: 'Run', kind: 'identifier', truncate: 'middle' },
  { key: 'status', header: 'Status', kind: 'status' },
  { key: 'sharpe', header: 'Sharpe', kind: 'number', digits: 2 },
  { key: 'cagr', header: 'CAGR', kind: 'percent' },
  { key: 'trades', header: 'Trades', kind: 'count' },
];

const HEAT_COLUMNS: DataTableColumn<(typeof HEAT_ROWS)[number]>[] = [
  { key: 'asset', header: 'Asset' },
  { key: 'address', header: 'Address', kind: 'identifier', truncate: 'middle' },
  {
    key: 'ic',
    header: 'IC',
    kind: 'heat',
    heat: { maxAbs: HEAT_MAX },
    format: (value) => formatSignedPercent(value as number, 2),
  },
];

function ExamplePage() {
  const [view, setView] = useState<View>('overview');
  return (
    <PageShell>
      <PageHeader title="breakout-follower v002" subtitle="Standalone qf-ui consumer" />
      <SegmentedControl
        ariaLabel="Page view"
        options={VIEW_OPTIONS}
        value={view}
        onValueChange={setView}
      />
      {view === 'overview' ? (
        <>
          <Section title="Equity">
            <MultiSeriesTimeChart title="Equity curves" series={LINE_SERIES} valueFormat="number" />
          </Section>
          <Section title="Session profile">
            <PriceProfileChart
              ariaLabel="Session price and profile"
              title="BTC session"
              xDomain={[SESSION_OPEN, SESSION_CLOSE]}
              price={{ key: 'close', label: 'Close', points: SESSION_POINTS }}
              profiles={[
                {
                  key: 'session',
                  label: 'Session profile',
                  color: chartColor(2),
                  rows: PROFILE_ROWS,
                  rowSize: 100,
                  band: VALUE_BAND,
                },
              ]}
              timeZone="utc"
            />
          </Section>
        </>
      ) : null}
      <Section title="Runs">
        <DataTable data={TABLE_ROWS} columns={RUN_COLUMNS} pageSize={10} sortable />
      </Section>
      <Section title="Information coefficient">
        <DataTable data={HEAT_ROWS} columns={HEAT_COLUMNS} />
      </Section>
      <Section title="Formatters">
        <FormatterList />
      </Section>
    </PageShell>
  );
}

// --------------------------------------------------------------------------- #
// App
// --------------------------------------------------------------------------- #

export function App() {
  const [railCollapsed, setRailCollapsed] = useState(true);
  return (
    <div className="app-theme flex h-dvh overflow-hidden">
      {/* The app frame (dock width, border, mobile drawer) is host-owned; utilities stand in. */}
      <aside
        className={`flex h-full flex-none flex-col border-r border-border-subtle bg-surface-sunken ${
          railCollapsed ? 'w-(--sidebar-width)' : 'w-(--sidebar-width-expanded)'
        }`}
      >
        <PrimaryRail collapsed={railCollapsed} onToggle={() => setRailCollapsed((c) => !c)} />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <SectionWorkspace navigator={<StrategyNavigator />}>
          <ExamplePage />
        </SectionWorkspace>
      </main>
    </div>
  );
}
