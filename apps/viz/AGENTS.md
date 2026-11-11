# Viz

## Codebase Architecture
- Use `apps/viz` for operator-facing exploration and read-only presentation of lake-backed outputs.
- When the user asks for a "dashboard" or "custom dashboard", add it to the Dashboards workspace and its `My dashboards` navigator under `/dashboards/*`, unless they explicitly name another destination.
- Public surfaces: DB API code in `apps/api/src/db_api`, DB API tests in `apps/api/tests`, and web app code in `apps/viz/web/src` (React + Vite SPA).
- Layout: `apps/api` is the FastAPI backend over lake-backed outputs; `web` is the React frontend; `scripts/dev.py` is the local dev launcher.
- Ownership: `apps/api` is a read-only/operator surface over `db/*` (its query rules: `apps/api/AGENTS.md`). `web` should consume the API surface rather than reading the lake directly.
- Preserve the FastAPI + React SPA split (not Next.js).

## qf-ui Boundary
- `apps/viz/qf-ui` (`@quant-factory/qf-ui`) is the portable UI kit: design tokens, base styles, primitives, layout, data, state, page frames, and the router adapter at the root export; charts behind the `/charts*` subpaths under `qf-ui/src/charts`; tables (primitives, `DataTable`, `MetricComparisonTable`, sort and column-format helpers) behind the `/tables*` subpaths under `qf-ui/src/tables`, the only place native table markup is rendered.
- `qf-ui/src/charts` is the only owner of frontend chart rendering and reusable chart behavior. It owns ECharts registration and lifecycle, primitives, chart chrome, legends, tooltips, axes, formatting, accessibility, in-chart responsive behavior, interactions, and reusable display transformations and toolbar controls.
- `apps/viz/web` owns fetching, validation, routes, dashboards, between-chart layout, and the declarative choice of chart type, placement, data, labels, colors, and enabled qf-ui chart capabilities.
- Do not implement feature- or page-local chart engines, ECharts options, chart interactions, chart styling, formatting, or transformation math. Add missing reusable behavior to qf-ui and consume it through the package's public API.
- Keep qf-ui portable: it must not import from `apps/`, `@/`, API modules, React Router, TanStack Query, or repository-specific data acquisition. In-app links reach the host router only through `QfRouterProvider`; ECharts is imported only under `qf-ui/src/charts`.
- Do not introduce a second chart engine, copied vendor chart code, or compatibility aliases such as `qf-charts` or `@quant-factory/qf-charts`.
- Building or restyling any page, dashboard or extension panel (in `web/` or `extensions/`): follow "Composing pages" in `qf-ui/AGENTS.md` and the UI invariants in `web/AGENTS.md`. `extensions/` has no AGENTS.md of its own, so these two files are its UI rules.

## Execution
- Keep the API read-only over canonical repo data surfaces.
- Do not duplicate the generic `/api/datasets` preview/query/stat routes under `/api/catalog` or `/api/features`.
- Keep the web app consuming the API surface rather than reading the lake directly.
- Run `apps/api` and `web` separately only when local debugging requires it.
