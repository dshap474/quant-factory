# DB API

## Codebase Architecture
- Serve generic parquet schema, preview, query, stats, and Arrow access through `/api/datasets/{scope}/...`; back it with `data.query`. `apps/viz/web` proxies `/api` to this service on port `8014`.
- Domain routers for catalog, features, backtests, signals, docs, and benchmarks (an empty registry extensions fill) may add UI-specific discovery or aggregation, but should not duplicate generic parquet query behavior.
- Layout: `src/db_api/main.py` wires the app; `src/db_api/routers/` owns HTTP routes; `src/db_api/dataset_charts.py` and `src/db_api/dataset_profiles.py` own UI-specific parquet chart/profile helpers; tests live in `tests/`.
- Query boundary: generic parquet reads use `data.query`, which picks the engine and returns Polars frames for JSON/Arrow serialization; routes never choose an engine.
- Absolute-path reads in routers go through `db_api.parquet` (`read_parquet_frame`, `read_parquet_schema`, `count_parquet_rows`), a thin adapter over `data.query`.

## Commands
- Bootstrap: `uv sync --frozen --group dev`
- Run API: `uv run --package quant-factory-db-api qf-db-api`
- Single test: `uv run pytest apps/api/tests/path/to/test.py::test_name -q`
- Targeted gate: `uv run pytest apps/api/tests -q`

## Execution
- Keep the API read-only. Do not write canonical data, feature, signal, or strategy artifacts from this service. The one exception is `POST /api/backtest-updates/{family}/{version}`, which starts `strategies.backtest_updates` and writes only that version's `updated/` folder.
- `src/` must not import any extension package; routes over installation-specific packages belong in `extensions/`.
- Do not add new direct `pl.read_parquet`/`pl.scan_parquet` generic readers in this service. Add missing generic behavior to `data.query`, then expose it through `/api/datasets` if needed.

## Gotchas
- ML Engine listing is window-bounded: `/api/ml-engine/runs` walks sidecar filenames newest-first (run IDs are timestamp-prefixed) and stops at `limit` plus a small reordering margin, so it must filter by producer/status *during* that read — never post-filter a page. `invalid_count` therefore covers only the files that read actually examined. `/api/ml-engine/producers` is the one deliberate whole-store scan; it exists so the operator filter cannot lose a family that a run flood pushed out of the newest page. Do not source filter options from the run list.
