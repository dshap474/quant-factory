# @quant-factory/qf-ui

Portable UI kit for quant-factory and future Quant Factory consumers: design tokens, base styles, primitives, layout, data tables, state, page frames, and ECharts-backed charts.

## Consumer setup

`examples/standalone/` is a complete host that reaches the kit only through package exports; `pnpm run example:check` type-checks and builds it, and `pnpm exec vite preview --config examples/standalone/vite.config.ts` serves the build.

1. **Install.** Add `@quant-factory/qf-ui` plus its peers: `react` and `react-dom` ^19, and `tailwindcss` ^4 with `@tailwindcss/vite` in the host's Vite config. Exports point at TypeScript source, so the host bundler compiles the kit (Vite does this as-is). ECharts, Base UI, cmdk, lucide and the IBM Plex fonts are regular dependencies.
2. **Stylesheet.** Tokens, base styles and the IBM Plex `@font-face` rules ship with `styles.css`; the host adds no fonts or tokens. `styles.css` also `@source`s the kit, so Tailwind emits the utilities it uses. Component CSS arrives with the JS imports.

   ```css
   /* Host global stylesheet */
   @layer theme, base, qf-components, qf-variants, components, utilities, qf-motion;
   @import "tailwindcss";
   @import "@quant-factory/qf-ui/styles.css";
   ```

   ```tsx
   import '@quant-factory/qf-ui/charts/styles.css'; // only when using /charts*
   ```

   The kit entries also import the layer statement first, so the order holds whatever the host's import order.
3. **Theme root.** Put `className="app-theme"` on the app's root element; the reduced-motion policy keys off it.
4. **Router.** Without a provider, links are plain anchors and navigation uses the History API. To route through the host router, wrap the app in `QfRouterProvider`. `Link` and `usePathname` are required; `useNavigate` and `useSearchParams` are optional. `examples/standalone/src/router.tsx` is a 60-line History API adapter.

   ```tsx
   const adapter: QfRouterAdapter = { Link: RouterLink, usePathname: () => useLocation().pathname, useNavigate };
   <QfRouterProvider adapter={adapter}>{app}</QfRouterProvider>;
   ```

5. **Shell.** The kit provides the rail (`SidebarShell rail` with `RailNavList` / `RailNavLink` / `RailNavDivider`), the navigator and the section workspace. The host owns the outer frame: the dock column that sizes the rail with `--sidebar-width` / `--sidebar-width-expanded`, and any mobile drawer.

The app shell pieces are portable too: `SidebarShell` (pass `rail` for the primary icon rail), `SectionWorkspace` / `SectionNavigator` (share the navigator width across sections with `SectionNavigatorWidthProvider`, or control it per navigator with `narrow` / `onNarrowChange`), `Navigator` with the pure `useTreeNavigatorState` (the host supplies a `useChildren` loader hook, so qf-ui never fetches), and `useSearchParamState` for one URL query parameter as state. A navigator's header band shows its `title` (the section label) and nothing else; collapse, search, the width toggle and `headerActions` render in its bottom bar (`SidebarShell collapsePlacement="bar"`), and rows are inset pills an equal 8px off both panel edges. The host keeps its own nav list, command menu, settings and data loaders.

## System

- **Shell boundaries:** header and navigator bands use the same `--shell-bar-height` (56px), including their border. The primary rail continues the top and bottom bar rules without shifting its icons. Adjacent panes share one boundary: navigators own the dividing edge; content must not add an outer border on that edge or wrap a shifted divider background onto it.
- **Tone:** every `tone` prop takes one vocabulary, `Tone = 'neutral' | 'info' | 'success' | 'warning' | 'critical'` (`StatusTone` adds `running`). Tokens `--color-tone-<tone>`, `-surface`, `-border`; helpers `toneTextClass`, `toneSurfaceClass`, `signTone`. `src/lib/tone.test.ts` pins WCAG contrast.
- **Control size:** `Button`, `Link` (control), `Input`, `SelectControl`, `SegmentedControl` take `size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'` (default `md` = `--control-height`); `Button`/`Link` take `icon` for square icon-only controls.
- **Stacking and motion:** z-index only through `--z-{base,lift,raised,sticky,dropdown,overlay,popover,toast}`. Only open/close moves: `.qf-motion-pop | -fade | -sheet-right | -sheet-bottom` key off Base UI's `[data-starting-style]`/`[data-ending-style]`; hover and press never animate; reduced motion zeroes `--duration-*`.
- **Spacing:** primitives own the rhythm. `PageShell` spaces its direct children `--gap-section` apart (`rhythm="block"`: `--gap-block` for pages of cards), with a toolbar or view switcher `--gap-block` above what it controls; the scrolling pane supplies the `--gap-block` top and `--inset-page` bottom edges. `Stack`, `Cluster`, `Grid` and `Columns` take role-named `gap` props (`xs` 4, `stack` 8, `heading` 12, `block` 16, `section` 32; each primitive accepts the subset that fits it), `Columns` lays explicit tracks that stack below a breakpoint (`template`, `from`, `rowGap`), and `Inset` pads a region inside a flush frame on the inset scale (`sm` 12, `md` 16, `lg` 24, `pane`, `tabs`; `axis` picks the edges). Children carry no outer margins.
- **Focus:** elements get the global `:focus-visible` ring; composite controls put `.qf-focus-within` on their wrapper so exactly one ring shows.
- **Heat and ids:** value-coloured cells use one scale, `divergingCellColor(value, { maxAbs, magnitude })` (sign picks the positive or negative chart tone, `magnitude` uses info; 14%-88% opacity by `|value| / maxAbs`), declaratively as `<TableCell heat={{ value, maxAbs }}>`. Ids, hashes and addresses render through `<Identifier truncate="middle">` or, in plain strings, `truncateMiddle(value)`; both keep 8 leading and 6 trailing characters.

## Overlays, command palette, data

Overlays are built on `@base-ui/react`: `Tooltip` (+ `TooltipProvider`), `Popover`, `InfoTip`, `Dialog`, `Sheet`, `DropdownMenu`, and toasts. Toasts are split so callers never load Base UI: `toast()` / `useToast()` live in a dependency-free store, and `<LazyToaster />` (mount once in the shell) loads the renderer on the first toast and flushes it.

```tsx
<LazyToaster />;                                   // shell
useToast().toast({ title: 'Copied', tone: 'success' }); // anywhere
<Tooltip content="Sharpe, annualised"><span>SR</span></Tooltip>;
```

`CommandPalette` (cmdk inside a Base UI dialog, generic and router-free) is exported from the root and from the `./command` subpath; hosts should `import()` the subpath lazily so cmdk stays out of the first load. `Kbd` renders key hints.

Data additions: `RollingNumber` (odometer digits with up/down flash, `aria-live` full value), `DataList` (semantic `<dl>`), and `DataTable virtualize` (`@tanstack/react-virtual`, on above `VIRTUALIZE_MIN_ROWS`; raise `maxRows` to use it).

## Charts

Charts live behind the `/charts*` subpaths so the root export never loads ECharts. They provide ECharts lifecycle ownership, line and categorical charts, compact charts, multi-series normalization and interaction, chart chrome, controlled brushes, optimizer grids, semantic themes, and public data contracts.

```tsx
import { LineChart, type QfSeries } from '@quant-factory/qf-ui/charts/renderers';
import '@quant-factory/qf-ui/charts/styles.css';

const series: QfSeries[] = [{
  key: 'strategy',
  label: 'Strategy',
  points: [{ date: new Date('2026-01-01'), value: 1 }],
}];

<LineChart series={series} height="100%" ariaLabel="Strategy equity" />;
```

Consumers may override the documented `--qf-chart-*` variables or map existing application chart variables at their CSS boundary. The package never fetches data.

For a complete analytical time-series surface, consumers provide only normalized series and optional product-owned controls:

```tsx
import { MultiSeriesTimeChart } from '@quant-factory/qf-ui/charts/renderers';

<MultiSeriesTimeChart
  title="Series overview"
  series={series}
  benchmark={referenceSeries}
  transformControls={{ zScore: true, ema: true }}
  headerRight={<ProductOwnedControl />}
  valueFormat="percent"
/>;
```

`MultiSeriesTimeChart` owns parsing, colors, dual-axis domains, benchmark rendering, legend visibility, hover, responsive geometry, downsampling, the date brush, and opt-in trailing Z-score and EMA controls. Benchmark series always use a dim dashed semantic-grey line on an independent hidden Y-axis. `isBenchmark` series never appear in the legend; the chart's dedicated `benchmark` overlay is listed as one toggleable legend entry so it can be named and hidden. Mark only contextual market overlays as `isBenchmark`; a strategy control or prior candidate belongs on the primary value axis as a normal solid series. Z-score and EMA windows use elapsed calendar days; when both are active, Z-score runs before EMA. Consumers retain data fetching and validation, thin source-to-series mapping, product copy, URL state, and between-chart placement.

For portfolio comparisons, `PortfolioDrawdownChart` from `/charts/renderers` uses the existing linked two-pane shell: values above, percentage drawdowns below, one legend, crosshair, tooltip and date brush. Supply portfolio-value series on a common scale (including any buy-and-hold comparison); every series uses the visible primary scale. Drawdown is value divided by its running positive peak minus one, calculated on all supplied observations before brush filtering. Missing values preserve the peak.

## Tables

`@quant-factory/qf-ui/tables` provides `Table` primitives and `SortHeader`, `DataTable`
for records, and `MetricComparisonTable` for comparisons. All table containers,
loading frames, and boxed metric strips use `--radius-surface` (8 px). Table frames
use a single 1 px `--color-border-subtle` edge, matching the chart frame's 6% hairline.
Headers, rows, and pagination share the enclosing frame. Wrap primitive tables in
`<Surface padding="none" clip>` around their ScrollArea; the frame stays visible
while the contents scroll and fade. Composed tables own their frame;
`DataTable flush` delegates it to its host, so nested frames never double the border. Headers use
`--color-surface-header`, mapped to the control surface step, above the data-row fill
`--color-surface-data`. Every table body uses the same subtle alternating-row tint
(`--color-state-stripe`), overridden by the shared hover and selected states. Pinned cells carry that same tint over an opaque
data surface. DataTable preserves absolute row parity through paging and virtualization;
group captions are excluded from striping. Default rows are 32 px high, with 12 px
horizontal cell padding and 16 px outer insets. Dense rows are 28 px high, with 8 px
horizontal cell padding and
12 px outer insets. These come from the table-height, spacing, and surface-inset tokens.
Use `TableCell wrap` for multiline content and `fullBleed` only for nested detail panels; mark their row `data-table-group`
so expanding a panel leaves data-row stripes stable. Navigation buttons inherit the
cell inset. Wide tables belong inside a `ScrollArea`.

For sanitized HTML such as Markdown, call `enhanceTableMarkup(article)` after insertion
and dispose its returned cleanup before replacement. It applies the same table recipes
and rounded, keyboard-scrollable frame; sanitization remains the host's responsibility.

`@quant-factory/qf-ui/tables/core`
holds the headless sort and column-format helpers (no DOM, no CSS). Table symbols are
exported only from these subpaths, never from the root. They fetch no data and carry
no strategy-specific metric conventions.

`DataTable` `columns` take bare keys (text, headed by the key) or `DataTableColumn`
objects that name a cell kind; the kit formats, aligns, tints and renders the value, so
pages pass data and options, never classes:

```tsx
import { DataTable, type DataTableColumn } from '@quant-factory/qf-ui/tables';

const columns: DataTableColumn<Run>[] = [
  { key: 'run_id', header: 'Run', kind: 'identifier', truncate: 'middle' },
  { key: 'status', header: 'Status', kind: 'status' },
  { key: 'sharpe', header: 'Sharpe', kind: 'number', digits: 2 },
  { key: 'cagr', header: 'CAGR', kind: 'percent' },
  { key: 'pnl', header: 'P&L', kind: 'money' },
  { key: 'trades', header: 'Trades', kind: 'count' },
  { key: 'ic', header: 'IC', kind: 'heat', heat: { maxAbs: 0.08 } },
  { key: 'launched', header: 'Launch (UTC)', format: (value) => formatUtc(value) },
  { key: 'name', render: (value, row) => <Link to={row.href}>{String(value)}</Link> },
];
<DataTable data={runs} columns={columns} pageSize={25} sortable />;
```

Kinds: `text` (default), `number` (3 decimals), `percent` (1), `money` (2), `count`,
`heat` (number tinted by `divergingCellColor`), `identifier` (`Identifier`) and `status`
(`StatusBadge`); `digits` changes the decimals. `format` replaces the text of any kind,
`render` the whole cell, `value(row)` derives the value (also used for sorting), `title`
sets the tooltip, and `truncate: 'end'` caps a long text column. Missing values show the
kit's em dash. Numeric kinds, and plain columns whose values are all numbers, right-align
header and cells; sortable numeric heads lead with the sort glyph, and an unsorted
column shows its glyph only on hover or focus.

```tsx
import { MetricComparisonTable, type MetricComparisonRow } from '@quant-factory/qf-ui/tables';

const rows: MetricComparisonRow[] = [
  { key: 'return', label: 'Total return', group: 'Returns', format: 'percent',
    emphasis: true, higherIsBetter: true, values: { candidate: .12, control: .09 } },
  { key: 'ratio', label: 'Risk ratio', group: 'Risk-adjusted ratios', format: 'number',
    description: 'Describe the convention used by your data source.',
    values: { candidate: 1.2, control: null } },
];
<MetricComparisonTable columns={[{ id: 'candidate', label: 'Candidate', detail: 'Selected' },
  { id: 'control', label: 'Control' }]} rows={rows}
  difference={{ current: 'candidate', reference: 'control' }} />;
```

Adjacent rows with the same `group` share a labelled group, separated by white space and one hairline; the table shrink-wraps to its columns up to the container. Omit groups for
a flat table. Use `description` for accessible metric help, `emphasis` for a key
outcome, and `format` (`percent`, `money`, `number`, `days`, `text`) for consistent
values. Missing and nonfinite values show a dash. Narrow containers scroll
horizontally while metric labels remain pinned; the region is keyboard scrollable.

## Execution chart module

`ExecutionTapeChart` from `@quant-factory/qf-ui/charts/execution` shows how one
order worked against the market: sampled depth behind a bid-ask band, trades as
bubbles sized by volume and colored by aggressor, the order path, fills, arrival
and average-fill levels, and a fill-progress pane. Hosts provide the data.

## Reusable orderbook chart module

Import `OrderbookLiquidityChart`, `OrderbookDepthChart`, and
`OrderbookChartControls` from `@quant-factory/qf-ui/charts/orderbook`. This is
the shared qf chart module; it contains no router, API client, or dataset access.
Hosts provide data and controlled state, so it works with any instrument or
venue. The controls support a UTC date/time jump, 1/3/6/24-hour windows, a price
range, and previous/next navigation. `1D` means 24 elapsed hours from the
selected UTC start, not an implicit calendar-day reset.

```tsx
import {
  OrderbookLiquidityChart,
  OrderbookChartControls,
  type OrderbookHeatmapData,
} from '@quant-factory/qf-ui/charts/orderbook';

// Data comes from the host. No fetcher is built into the chart.
<OrderbookChartControls
  start={start} first={first} last={last} hours={hours} bandPercent={bandPercent}
  onStartChange={setStart} onHoursChange={setHours} onBandPercentChange={setBandPercent}
/>
<OrderbookLiquidityChart
  data={data} selectedIndex={selectedIndex} onSelect={setSelectedIndex}
  ariaLabel="ETH orderbook liquidity" sizeLabel="Size (ETH)"
/>
```

`OrderbookHeatmapData` contains `snapshots` (`timestamp` in Unix seconds and
`midprice`), `cells` (`[snapshotIndex, priceBinIndex, size]`), `price_min`,
`price_step`, and `price_bins`. The chart retains click/arrow-key selection, a
true UTC time axis, a dark linear size scale, midpoint overlay, and hover
crosshair. Supply verified units via `sizeLabel`; the default labels provider
units without inferring BTC or USD. Depth receives intact `price/size/side`
levels, `midprice`, and a controlled `cumulative` flag.

The module exports `OrderbookScaleMode` (`relative` or `historical`) and
`OrderbookHistoricalScale` (`p50`, `p90`, `p95`, `p99`, `priceStep`). Pass
`scaleMode` and `historicalScale` to the heatmap, and `scaleMode` /
`onScaleModeChange` to the controls. Relative uses the maximum supplied cell
size; Historical uses five fixed percentile bands with a labeled legend. The
renderer never computes or fetches a historical baseline, and rejects a
baseline whose `priceStep` differs from the supplied heatmap. Hosts own the
calibration method, time coverage, provenance, and loading/error handling.
Changing the mode only changes color encoding; sizes and depth selection are
unchanged.

### Complete panel

`OrderbookPanel` composes the portable controls, heatmap and selected-book depth
frames, depth display toggle, loading/empty/error/retry states, and optional
notes. Pass controlled `controls`, `selectedIndex` / `onSelect`, and `depthMode`
/ `onDepthModeChange`. Its `heatmap`, `depth`, and `historical` source props each
carry `{ data, loading, error, onRetry? }`; the host owns fetching and
persistence. No API or router is imported by the panel.

Heatmap cells optionally include bid/ask sizes as
`[snapshotIndex, priceBinIndex, totalSize, bidSize, askSize]`; existing three-value
cells remain supported. Tooltip quantities use up to fifteen significant
digits and show the Relative percentage of the window maximum or the
Historical percentile band. Bid/ask rows appear only when supplied by the host.
