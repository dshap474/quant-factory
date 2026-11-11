# viz/web

## Scope
- `apps/viz/web` is the **React + Vite** operator frontend for `quant-factory`, consuming the read-only `apps/api` FastAPI backend.
- Read-only operator visualization: schema, preview, query, stats, and Arrow data flow in from `/api/datasets/{scope}/...`.
- Public surfaces: app code under `src/lib/`, `src/pages/`, and route table in `src/routes.tsx`.

## Codebase Architecture
- Stack: React 19, Vite 7, React Router 7, TanStack Query 5, Tailwind v4, TypeScript strict, the local `@quant-factory/qf-ui` workspace kit (components, tokens, and charts over ECharts 5.6), Zod, openapi-fetch, marked + DOMPurify. Package manager is **pnpm** (the repository-root `pnpm-lock.yaml`, exact pins).
- Data layer: generated OpenAPI types under `src/lib/api/generated/`; domain modules export fetchers + `use*` hooks. TanStack Query is the only server-state cache.
- Consumes the parent `apps/api` over `/api/*` and `/health`; do not read parquet from `db/` directly.

## Commands
- Install: `pnpm install`
- Dev server: `pnpm dev` (port 5174)
- Build: `pnpm run build`
- Typecheck: `pnpm run typecheck`
- OpenAPI: `pnpm run generate:api` / `pnpm run check:api`
- Unit tests: `pnpm test`
- E2E smokes: `pnpm run test:e2e`
- Fast gate: `pnpm run gate:fast` (lint + typecheck + test)
- Full gate: `pnpm run gate:full` (lint + typecheck + test + build + e2e)

## Execution
- Keep this app read-only over canonical repo data surfaces; never write to the lake from the UI.
- Route all parquet/dataset reads through the `/api/datasets/{scope}/...` surface served by `apps/api`.
- Preserve React + Vite + Tailwind v4; do not introduce Next.js or a second server-state cache.
- Route every chart renderer through declared `@quant-factory/qf-ui/charts*` exports. Direct ECharts imports in Viz, qf-ui internal-source imports, and Visx renderers are forbidden. D3 scale math may remain in Viz when it supports non-rendering interaction geometry.
- Use Zod for runtime validation of API payloads at trust boundaries.
- Sanitize backend-supplied markdown through DOMPurify before rendering.
- Run `pnpm run gate:full` locally before publishing changes that touch UI surface or build configuration.

## UI Invariants
- UI-source invariant: every rendered element comes from the shared design system: the portable `@quant-factory/qf-ui` kit plus the app-bound `src/ui/` layer (shell, section frames, router provider). Consumers import both only through the `@/ui` barrel, which re-exports the qf-ui root; chart and table subpaths (`@quant-factory/qf-ui/charts*`, `@quant-factory/qf-ui/tables*`) are imported directly, and table symbols exist only there. Shared UI imports its own siblings relatively. Pages, dashboards, and extensions compose those components and own no styling: `src/app.css` is the one stylesheet outside shared UI and is import-only; native `<button>`, `<input>`, `<select>`, `<textarea>`, and the `<table>` family never appear outside shared UI; page `className` carries layout utilities only, with color, border, shadow, radius, overflow, and viewport sizing living in a shared component or variant; raw color literals live only in `qf-ui/src/styles/tokens.css`; CSS radius is `0` or a radius role token (`--radius-badge`, `--radius-control`, `--radius-surface`, `--radius-dialog`, `--radius-pill`); elevation comes only from the `--shadow-raised`, `--shadow-overlay` and `--shadow-dialog` tokens; and type comes only from the `--text-<role>` tokens, with Plex Mono reserved for ids, hashes, paths and code and uppercase reserved for the overline role. A missing portable recipe is added to `qf-ui/src/` (app-bound ones to `src/ui/`) and consumed everywhere, never re-implemented at a call site. `pnpm run check:ui` enforces this unconditionally: it has no allowlist and must never be given one.
- Selection-bar invariant: every list, menu, select, command palette and table body uses one recipe: the pointer or keyboard highlight is `--color-state-hover`, and the selected, checked or current row is `--color-state-selected` (`--color-state-selected-hover` while hovered). Route tabs mark the current route with a 2px `--color-brand` underline; segmented controls mark the chosen option with a raised pill. Section-navigator rows are inset pills (8px off both panel edges on a `--radius-control` fill); the current row is marked by the selected fill and weight 500 alone. Neither the section navigator nor the primary-sidebar rail ever draws a gold bar. Settings and collapse controls, toggles, and action buttons never draw a bar.
- Primary-sidebar collapse invariant: brand, route, settings, and disclosure icons keep identical x/y centers in expanded and collapsed states. Give each a permanent `--shell-slot` (32px) leading slot centered at x=24 in the 48px rail, preserve footer order, and expand rows only to the right; never re-center icons between states, and never size shell slots from `--control-height`. Section navigators show only their section title in the 56px header band; every navigator control (collapse, search, width toggle) renders in the 49px bottom bar (8px above and below the 32px controls) on the primary rail's bottom-toggle row, and the collapsed expand tile floats at that same spot.
- Chart-engine invariant: every production chart, heatmap, optimizer surface, sparkline, histogram, and time-range brush renders through `@quant-factory/qf-ui/charts*`; `apps/viz/qf-ui/src/charts/core/QfChart.tsx` is the sole ECharts lifecycle owner.
- Chart-geometry invariant: every full analytical chart frame uses the shared `QF_CHART_ASPECT_RATIO` (`16:9`) without page-local height or ratio overrides; multi-pane stacks declare each pane `main` or `study` and take the package-owned `multiPaneAspectRatio` (main + study `4:3`, plots `3:1`), never a page-local ratio or row weight. Compact sparklines and histograms are micro-visualizations and retain host-controlled dimensions. The legend sits in the frame's right-hand rail (`--qf-chart-legend-width`) beside the plot, stacking under the plot only on a phone (a 720px viewport, or a chart cell 360px wide or less; a cell up to 720px keeps the rail on a slimmer 9rem track); the frame ratio, not the plot ratio, is the invariant.
- Loading-state invariant: route and filter controls update immediately. Pending or placeholder query data renders localized shared skeletons in stable geometry; never paint stale results for newly selected parameters or use text-only loading empty states.
- Hover-state invariant: buttons, table rows, and navigation targets switch immediately to the shared `--color-state-hover` overlay; press switches to `--color-state-pressed` (primary-sidebar rail links have no press state: a click marks the item current immediately), and selected rows use `--color-state-selected` (`--color-state-selected-hover` while hovered). Do not animate hover color, background, border, or shadow, and never scale on press; state-change motion such as icon swaps, disclosure chevrons, and shell movement may remain.
- Page-composition invariant: every page, dashboard and extension panel follows "Composing pages" in `apps/viz/qf-ui/AGENTS.md` (frame, controls, content order, card treatment, spacing ladder). Read it before building or restyling a page.
- Viewport-containment invariant: the app shell and desktop section workspaces fit the dynamic viewport. Primary and secondary navigators, tables, and bounded content panes own their overflow with internal scrollbars; never grow panel content into a document-level scrollbar. When `.route-content` hosts a section workspace it has no padding and never scrolls; the workspace panes carry `--inset-page` and own every scrollbar. Never cancel a parent's padding with negative margins.
