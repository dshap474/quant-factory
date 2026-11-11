<!-- Purpose: operating guide for the React visualization app. Usage: start with Commands, then consult Architecture for runtime boundaries. -->

# viz-web

React + Vite SPA for the quant-factory operator visualization dashboard.
Consumes `apps/api` via `/api` (and `/health`) proxy to port 8014.

Selecting a family in Features opens its workspace over the family's full published
panel, with its snapshot and analysis status. The `tab` URL parameter preserves the
selection across the Features, Data, Correlation
and IC tabs (an installed extension may add asset-panel tabs through the
`featureWorkspace` hook in `src/extensions.ts`). Curated presets are column views of the same
published data; unbuilt configurations have no inferred statistics. Unpublished
local builds are not exposed by this read-only surface. Analysis is withheld
when its source build and selected columns cannot be verified.

## Stack

- React 19 + Vite 7 SPA (not Next.js)
- React Router 7 (library mode)
- TanStack Query 5 (server state)
- openapi-typescript + openapi-fetch (generated paths)
- Zod 4 (response trust boundaries)
- local `@quant-factory/qf-ui` kit (components, tokens, and ECharts charts)
- Tailwind CSS v4
- Biome (format) + ESLint (correctness)
- TypeScript strict + Vitest + Playwright

## Commands

```bash
pnpm install
pnpm dev            # http://127.0.0.1:5174  (/api + /health → localhost:8014)
pnpm run generate:api
pnpm run check:api
pnpm test
pnpm run test:e2e
pnpm run test:e2e:integration  # real FastAPI + disposable parquet fixture
pnpm run gate:fast  # lint + typecheck + test
pnpm run gate:full  # + build + bundle closure + mocked e2e + real-API smoke
```

From `apps/viz/`:

```bash
cd ../..
just dev    # idempotently start DB API + React app on available ports
just kill   # stop only the processes owned by just dev
```

`just dev` prefers API port `8014` and web port `5174`, then scans upward when either is
occupied. Set `VIZ_API_PORT` or `VIZ_WEB_PORT` to change the preferred starting ports. The command
prints the selected URLs and reuses them on subsequent runs while the stack is healthy.

## Layout

| Path | Role |
|------|------|
| `src/lib/api/` | Generated OpenAPI client, domain hooks, Zod boundaries |
| `src/lib/components/Dataset*.tsx` | Catalog explorer, parquet table, feature atlas, and analysis workspaces |
| `src/lib/components/charts/` | Product-specific chart adapters and data composition |
| `src/pages/` | Route pages |
| `e2e/` | Playwright smokes |

The Data and Features routes expose logical layer/domain/version navigation, physical file
exploration, paginated parquet tables, multi-cell charts, feature profiles, and correlation/IC
analysis without writing to the lake. The sidebar settings menu switches between catalog and
explorer views and persists the app-wide preview row count in local storage.

## Architecture

- Route pages are loaded with `React.lazy`; chart-heavy catalog panels are deferred again until
  selected. Keep the shell and tiny fallbacks eager.
- TanStack Query owns remote API state. Shareable catalog controls live in URL search parameters;
  transient hover, brush, and local chart presentation state stays in components.
- React Compiler is enabled, so manual `useMemo` and `useCallback` should be added only when an
  external identity contract requires them.
- Markdown from the API is sanitized with DOMPurify immediately before the only HTML injection
  sink.
- `@quant-factory/qf-ui/charts*` owns reusable chart rendering and in-chart interaction. Viz chart
  consumers retain fetching, trust-boundary validation, thin data mapping, product-specific
  controls, copy, URL state, and between-chart placement.

## Dependency policy

The root `pnpm-workspace.yaml` enforces a seven-day minimum package age and no-downgrade trust
policy. Keep exact versions and the root pnpm lockfile as the single dependency source of truth.

### Extensions

Each `../extensions/<name>/extension.tsx` default-exports a `VizExtension` from
`src/extensions.ts`, discovered at build time. An extension declares an `id` and a `mount`,
optional `routes` under that mount, and any of the hooks typed there (`featureWorkspace`,
`section`, `strategyPresentation`, `opsPanels`, and the others); `dashboardNavigation()` and
`executionNavigation()` collect the `navigation` entries of extensions mounted at
`dashboards` and `execution`, for the page or `section` owner that renders them. Duplicate owners and
conflicting routes fail at startup. With no extensions installed the app runs on its core
pages.

### Strategy performance comparisons

A strategy extension may add its own tabs and diagram pages; each documents them in its
own `README.md` under `../extensions/<extension>/`.

Every strategy chart uses qf-ui charts, including the legacy equity adapter. Current candidates
and their registered strategy controls share the primary value axis. Benchmarks are
registered with the API (`GET /api/benchmarks`, none by default): the research strategy
chart draws its buy-and-hold overlay on that primary axis, hidden from the legend; other
strategy charts use `isBenchmark` for the grey dashed overlay on an independent hidden scale. An extension adds table rows with
`strategyPresentation.extraMetrics`; a section's navigator and index page come from the
`section` hook (read by the Execution section).
`MetricComparisonTable` (from `@/ui`) owns metric-table layout, numeric formatting and
optional current-minus-comparison differences. The strategy and signal research surfaces
and the optimizer and categorical grids consume this same component. Shared strategy metric definitions
live in `lib/components/strategies/performance-metrics.ts`.

The selected-run comparison takes priority over historical baseline overlays. A current-data
replay or historical fallback is labeled separately and does not receive a same-run difference
column. UI selection never promotes a candidate or rewrites a sealed research artifact.

### Raw orderbook charts

The Chart tab for orderbook `raw/1m/.../orderbook/*_levels.parquet`
consumes the reusable `@quant-factory/qf-ui/charts/orderbook` module for
a liquidity heatmap with a midpoint overlay and click/arrow-key selection
of the full selected book's depth. Use the UTC date/time picker and Jump button to select a window within the
current monthly file. Choose a 1-, 3-, 6-hour, or 1D (24-hour) window and a
midpoint range or all stored levels. Heatmaps retain at most 180 sampled books
and sum complete levels into zero-aligned 100-quote-price-unit bins; depth retains all source
levels and offers cumulative or per-band display. Same-timestamp books with
different midpoints remain distinct. Sizes are unverified provider units,
not inferred BTC or USD. The view is read-only and never fills missing minutes.

The Scale toggle selects Relative (zero to the visible window maximum) or
Historical (pooled same-provider/exchange/product P50/P90/P95/P99 thresholds).
Historical uses sixteen evenly spaced minute snapshots per stored monthly
partition, across all available history; its date range and sample count are
shown below the charts. It is a sampled descriptive baseline, not a trailing
or point-in-time indicator. The visible price-range filter crops whole bins
after summing, so both modes retain identical bin quantities.

The Viz orderbook workspace is a fetching/persistence adapter for the complete
`OrderbookPanel` in the shared chart module. The panel owns the two frames,
window/scale/depth controls, loading/error/retry presentation, and chart notes.
Heatmap tooltips expose numeric total size, bid/ask components when supplied,
and the active scale reference. Validated local preferences are stored per
monthly dataset path: start, duration, range, scale, depth mode, and selected
timestamp/midpoint. Reopening that dataset restores its Chart view. Corrupt or
unavailable browser storage falls back to the default view.

All raw 1m provider orderbook `*_levels.parquet` datasets open directly in the
reusable orderbook Chart view, in both the logical catalog and physical file
explorer. Recognition is provider-independent. Table and Features remain
available through the preview tabs; derived metrics retain their time-series
charts. Dense archives are read in bounded one-hour chunks.
