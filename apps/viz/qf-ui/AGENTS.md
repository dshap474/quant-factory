# qf-ui

## Scope

Portable Quant Factory UI kit. The root export owns design tokens, base styles, primitives, layout, data, state, page frames, the portable app-shell pieces (sidebar shell, section workspace, tree navigator), and the router adapter. `src/tables` (the `/tables*` subpaths) owns every table: primitives, sort headers, `DataTable`, `MetricComparisonTable`, cell rendering and the headless sort/format helpers in `tables/core`. `src/charts` (the `/charts*` subpaths) owns React/ECharts rendering: chart lifecycle, registration, primitives, chrome, theme interpretation, formatting, accessibility, and in-chart responsive behavior. Applications own fetching, validation, routes, dashboards, between-chart layout, and their shell composition (nav list, command menu, settings, data loaders).

## Commands

- `pnpm lint`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build`

## Boundaries

- Never import from `apps/`, `@/`, API modules, React Router, TanStack Query, or another repository. In-app links go through `useQfRouter()`; hosts supply their router with `QfRouterProvider`.
- Do not add a second chart engine, compatibility alias, or application data acquisition.
- Import ECharts only under `src/charts`, and keep all ECharts registration and lifecycle code under `src/charts/core`. The root barrel must never reach `src/charts`.
- Popups are Base UI only (`@base-ui/react`); do not add Radix packages beyond the existing Select. Toast callers use `toast-store.ts`, never `Toast.tsx`, so Base UI stays out of their chunks.

## Rules

- Repo-wide split: `src/` is generalized public core; private, user-added implementations live in
  a package's `extensions/`, never in `src/`. qf-ui has no `extensions/` — it is public core
  only, so nothing private or application-specific belongs here.
- Keep React and React DOM as peer dependencies; qf-ui owns the pinned ECharts dependency.
- Public consumers use declared exports only. Do not expose application aliases, API models, routes, query state, or page layout.
- Preserve chart geometry, semantic CSS tokens, accessibility, and interactions unless an accepted specification explicitly changes them.
- Benchmark overlays always use an independent hidden Y-axis. `isBenchmark` series NEVER appear in legends; `MultiSeriesTimeChart`'s dedicated `benchmark` overlay is the one exception, listed as a toggleable entry so it can be named and hidden. Enforce this in shared chart components, not individual pages. Benchmark lines are dim dashed `--color-chart-benchmark`, a neutral that is never a palette slot; ordinary legend lines are solid.
- Lines are linear by default. Held, position, count and regime data declare `interpolation: 'step-end'` at the call site. Smoothing is opt-in (`interpolation: 'smooth'`) and always carries a visible `ChartNote` reading "Smoothed"; shared frames add it automatically, and callers framing a bare `LineChart` or `Sparkline` add it themselves. Chart series 1 is always the brand color (gold by default): `--color-chart-1` is `var(--color-primary)`, so the primary series of every chart renders in the brand color, and `--color-chart-primary` names the same colour for explicit primary marks. The legend sits in a right-hand rail beside the plot.
- Every `tone` prop uses the one `Tone` vocabulary from `src/lib/tone.ts`; never add a component-local tone set. Status text maps to a `Tone` only through `statusTone()` in the same module, applied to the exact string the user sees.
- Sized controls use the `ControlSize` scale (24, 28 and 32 in production); z-index uses the `--z-*` scale; focus is one 2px `--color-focus-ring` outline (offset 0 on controls, -2px inside scroll containers), never a border-color change; hover and press never animate, and only open/close uses the `.qf-motion-*` recipes.
- Tokens are roles, not values: surfaces are `--color-surface-{sunken,canvas,raised,control,overlay}`, text is `--color-fg-{primary,secondary,tertiary,disabled}`, status is `--color-tone-*`, and type is `--text-<role>`. The brand color (`--color-brand`, gold by default) marks only the primary button, the active route tab, the section navigator's current-row bar, text selection and chart series 1; the primary rail draws no brand bar. Chart CSS reads only `--qf-chart-*` bridges, and each bridge reads a host `--color-*`, `--font-*`, `--radius-*`, `--shadow-*` or `--text-*` token with a full-color fallback. HSL triplets are not used.
- Layout primitives own the space between their children: `PageShell` spaces its direct children on the page rhythm (`rhythm`), `Stack`, `Cluster`, `Grid` and `Columns` own their `gap`, and `Inset` owns an edge inside a flush frame; children carry no outer margins. Gap props name spacing roles (`xs`, `stack`, `heading`, `block`, `section`), each mapped to its `--gap-*` token, never sizes, and there are no `sm`/`md`/`lg` aliases.
- No caption clutter. Section, chart and page headers carry a title and controls only; never fill a `right`, `headerRight` or `footer` slot with small grey status text (cursor dates, "row 250 of 250", "latest N of M", "newest first", "pick another in …"). A value the reader needs is a `StatItem`, a table cell, a control's own label (the scrubber shows its position) or part of the title; anything else is dropped. Captions are for explanatory prose in its own section (assumptions, method notes), never decoration.
- Every public prop and return type is named and exported.
- Run lint, typecheck, test, and build before handing off changes.

## Composing pages

These rules bind every consumer that builds pages from qf-ui (`apps/viz/web` pages and dashboards, `apps/viz/extensions`), not only qf-ui itself.

- Frame: a detail page is one `TerminalPage`. Its header band carries identity and navigation only: `kicker`, `title`, route `tabs`, state `badges`, and machine facts in `right`. Never put controls, prose or loading text in the band.
- Page-wide controls (observation day, scope, asset) go in `TerminalPage`'s `toolbar` slot: one right-aligned row that opens the body, labels inline with their control (`Field layout="inline"`), one `--gap-block` above the content it governs. Controls that filter one section live inside that section, left-aligned in a `Cluster` directly above the table they filter. Never hand-roll the row with `Cluster justify="end"` on the page.
- Content order: every page, dashboard, and extension panel leads with its chart; tables follow; prose comes last. A page carries at most one prose section, placed below the charts and tables, and the page header's `right` facts or a section's `right` badge carry state (verdict, run id, lifecycle) instead of a paragraph. Never stack explanatory text above the first chart, and never add a text-only section to introduce a chart.
- Lead with one full-width primary chart (`ChartFrame`) that answers what the page is about; peer charts that compare like with like share a `ChartGrid`. Detail pages are one column: width comes from the frame, and only search inputs take a max width.
- Sections are open, content is carded: a `TerminalSection` title sits on the page canvas, and only the things inside it are surfaces (`ChartFrame`, a framed `DataTable`, an `IndexList`). Never box a section or nest a card inside a card.
- Inside a section, blocks stack on `Stack gap="block"`; a heading's controls row and its table stack on `gap="heading"`.
- Links to a page's sub-pages are an `IndexList` of `IndexBar`s titled `NN / Name` (`01 / Overview`), each with a one-line description that names live counts (`120 assets · 95 eligible`), never a bare link list or a grid of cards.
- Spacing: one 4px scale (Tailwind 4, 8, 12, 16, 24, 32, 40, 48, 64; 2px and 6px only inside components), and space encodes grouping on one ladder: `--gap-stack` 8 < `--gap-heading` 12 < `--gap-block` 16 < `--gap-section` 32, so a heading sits closer to its content than to the previous section. Every gap has one owner: the parent layout primitive (`PageShell` rhythm, `Stack`/`Cluster`/`Grid`/`Columns` `gap`, `Inset` for an edge inside a flush frame), and children carry no outer margins; nested containers never stack padding on a shared side. The page rhythm is fixed: header or toolbar to first content is `--gap-block` (the scrolling pane's top edge), sections are `--gap-section` apart (`PageShell rhythm="block"` for pages of cards), a view switcher or toolbar sits `--gap-block` above what it controls, and a scrolling page ends on `--inset-page`. Layout spacing goes through primitives; only component internals use raw 0-8px values. `pnpm run check:ui` rejects, outside shared UI, padding, margin, gap and space utilities of 12px or more (every axis, side and negative) and arbitrary `[var(--gap-*)]`/`[var(--inset-*)]` spacing, and any spacing utility on a `PageShell`, `Section`, `Stack`, `Cluster`, `Grid` or `ChartGrid` `className`. A relationship no primitive expresses is added to `qf-ui/src/layout/`, never allowlisted.
