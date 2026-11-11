# viz

Operator visualization dashboard for quant-factory.

## Installation

```bash
# From the repository root
uv sync --frozen --group dev
pnpm install --frozen-lockfile
```

## Overview

The viz package provides a full-stack dashboard for viewing:
- Backtest results and equity curves
- Signal predictions
- Feature statistics and correlations
- Data catalog browsing

## Quick Start

```bash
# From the repository root:
just dev        # start or reuse the app
just kill       # stop this checkout's app processes
just help       # list all repository commands

# Or separately:
# Terminal 1 - DB API
uv run qf-db-api

# Terminal 2 - Web (React + Vite)
pnpm --dir apps/viz/web dev
```

Access at:
- Friendly Web UI: http://quant-factory.localhost:5174
- Web UI: http://127.0.0.1:5174
- DB API: http://localhost:8014

`just dev` prints the named HTTP address with the selected web port without opening
a browser. Use `DEV_OPEN=1 just dev` to open it explicitly. Modern browsers
resolve `.localhost` names to your own computer; no proxy, certificates, or machine
setup is required. The servers bind only to loopback. Vite forwards API requests
and hot-reload WebSockets work through the same address.

If a preferred port is occupied, the launcher selects the next available port and
prints the actual URL. `just dev` reuses a healthy stack; `just kill` stops this
checkout's app processes. After a reboot, run `just dev` again.

With `VIZ_API_URL` set, the launcher starts only the web app and proxies `/api` to
that existing DB API. Use it to point a checkout without a local lake (`db/data`) at a DB API running
elsewhere.

## Architecture

```
apps/viz/
├── qf-ui/               # Portable UI kit: tokens, components, frames, ECharts charts
├── web/                 # React + Vite frontend (port 5174)
│   ├── package.json     # pnpm, gate:fast / gate:full
│   ├── src/
│   │   ├── lib/         # API, charts, shared UI
│   │   ├── pages/       # Route pages
│   │   └── routes.tsx
│   └── e2e/             # Playwright smokes
└── scripts/
    └── dev.py           # Launch DB API, local control, and web
```

All `/api` routes are served by the sibling `apps/api` service on port 8014.
The web app proxies `/api` and `/health` to that service and reads nothing from
the lake directly. `scripts/dev.py` also launches a development control server
when an installed extension provides a `development.json` descriptor.

## Gates

```bash
cd apps/viz/web
pnpm run gate:fast   # lint + typecheck + unit tests
pnpm run gate:full   # + production build + Playwright e2e
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/backtests` | List all backtests |
| `GET /api/backtests/{strategy}/{run}` | Backtest detail |
| `GET /api/datasets/{scope}/schema/{path}` | Generic parquet schema + row count |
| `GET /api/datasets/{scope}/preview/{path}` | Generic paginated parquet preview |
| `GET /api/datasets/{scope}/query/{path}` | Generic projected/filtered DuckDB parquet query |
| `GET /api/datasets/{scope}/stats/{path}` | Generic numeric parquet stats |
| `GET /api/datasets/{scope}/arrow/{path}` | Generic Arrow IPC query response |
| `GET /api/features` | List feature categories |
| `GET /api/signals` | List signals |
| `GET /api/catalog` | Browse db/ directory |
| `GET /api/docs/tree` | List docs navigation tree |
| `GET /api/docs/page/{path}` | Return markdown for one docs page |

## Stack

- **Frontend:** React 19, Vite 7, React Router 7, TanStack Query, Tailwind v4, qf-ui (components + ECharts charts), Zod, pnpm
- **Backend:** FastAPI (`apps/api`), DuckDB via `data.query`
