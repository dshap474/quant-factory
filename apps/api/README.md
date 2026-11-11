# quant-factory DB API

Read-only FastAPI wrapper over `data.query` for bounded lake dataset access.

Run locally:

```bash
uv run qf-db-api
curl http://localhost:8014/health
curl http://localhost:8014/api/datasets/data/schema/<lake-relative-file>.parquet
```

Generic parquet routes:

- `GET /api/datasets/{scope}/schema/{path}`
- `GET /api/datasets/{scope}/preview/{path}`
- `GET /api/datasets/{scope}/query/{path}`
- `GET /api/datasets/{scope}/stats/{path}`
- `GET /api/datasets/{scope}/arrow/{path}`

Write routes (POST/PUT/PATCH/DELETE) refuse requests whose browser `Origin` is not local
(loopback, `*.localhost`, or `DB_API_CORS_ORIGINS`), so another website cannot trigger
a refresh or backtest update; clients that send no `Origin` (curl, scripts) are unaffected.

Supported scopes are `data`, `features`, `signals`, `strategies`, and `research`. The source of truth is parquet under `db/`; DuckDB is the embedded runtime used by `data.query`.

The lake root comes from `QUANT_DB_ROOT` (or `DB_API_DB_ROOT`); package discovery for
research, docs and feature catalogs reads the repository checkout (`DB_API_REPO_ROOT`,
default: this repository), so a lake kept elsewhere still finds its packages.

Opaque entity keys (e.g. UUID asset IDs) get human labels from the optional
`extensions/entity-labels.json` rule list (`db_api.entity_labels`): each rule maps an
identifier column under a path prefix to a lookup parquet's label and detail columns.
Chart values return a `labels` map, series labels and profile Top/Bottom rows use it,
and value search matches labels as well as keys. Values stay machine identifiers.

Catalog display names come from the optional `extensions/catalog-labels.json` plain
string dictionary, loaded once when the API starts. Keep instance-specific provider
spellings there; restart the API after edits. Apps without an extension root
use an empty dictionary and humanized provider fallbacks. `GET /api/catalog/labels`
serves this metadata without scanning the lake. Logical catalog items expose parallel
`category_labels`, overview nodes and file-browser entries expose `label`, and listings
expose `path_labels` for breadcrumbs. Original names, IDs, paths, and facet values remain
machine identifiers. A dictionary key may be a full family path when a dataset needs an
explicit title. Unknown non-provider directories and file names stay literal.

Feature family diagnostics use `GET /api/features/overview/{path}`. The response
describes the actual published parquet, registered preset definitions, exact
column-subset views, monthly finite-cell coverage, and quality by inferred block.
The first request profiles numeric columns in batches of 32 on the shared DuckDB
connection (`duck.py` sets its thread count and memory limit). Snapshot results are cached in memory and
in `$XDG_CACHE_HOME/quant-factory/feature-overview` (default
`~/.cache/quant-factory/feature-overview`), outside the canonical lake. Both caches
invalidate when the parquet modification time or size changes; the disk cache
survives API restarts. A newly published snapshot still requires one full scan.
`?diagnostics=false` reads only the schema and timestamp/asset keys, returning
preset column contracts without quality statistics. The web workspace requests
only this form.
No producer is constructed or run. Configurations without a selected-column
contract remain unbuilt, and analysis artifacts without proven source lineage
remain unverified. `/api/features/profile/{path}?preset=<name>` projects the
registered subset before profiling, sorting, or paging.

## Extensions

Each direct child of `extensions/` (names starting with `_` are skipped) holds an
`extension.py` with `register(app)`, called by `create_app()`; `create_app(load_extensions=False)` loads
none. An extension may add routes (it may not repeat a core method and path) and
may register into the core registries. These are kept per application and start
empty on each one:

- `routers.benchmarks.register_benchmark(app, ticker, description, loader, *, label=None)`: a
  daily `[timestamp, close]` series served at `/api/benchmarks/{ticker}` and listed
  at `/api/benchmarks`.
- `research_supplements.register_surface_supplement(app, label, loader)`: a
  research-surface supplement, loaded when the run manifest's provenance declares
  `label` and returned under `supplements[label]`; the web app charts the first one
  shaped as a variant matrix.
- `catalog_labels.register_raw_family_rule(app, prefix, depth, second_levels)`:
  collapses raw paths under `prefix` to their first `depth` parts in the catalog;
  `second_levels`, when given, limits the rule to those second path parts.
- `routers.research.register_research_catalog_entry(app, ...)`: a research package
  listed in the research catalog.

These are process-wide (a module-level list or value, shared by every application
created in the same process):

- `routers.backtest_engine.register_run_source`, `register_asset_source` and
  `register_execution_source`: extra run listings and the asset and Rebalance day
  routes for a family's runs.
- `feature_overview.register_asset_ic_status`: the reader behind `analysis.ic` for
  asset panels (otherwise `missing`).
- `http_cache.register_no_store_prefix`: marks routes under a prefix `no-store`.


Orderbook visualizations use `GET /api/catalog/orderbook/heatmap/{path}` with
optional `start` (Unix seconds), `hours` (1–24), and `band_percent` (0 for all
levels), plus `GET /api/catalog/orderbook/depth/{path}` with the selected
`timestamp` and `midprice`. `orderbook_charts.py` projects five raw columns
through `data.query`, discovers timestamp/midpoint keys before sampling and reads levels in
one-hour chunks bounded to 300,000 levels each. Oversized chunks or windows
over 10,000 books are rejected rather than truncating a book. Heatmaps sample at most 180 distinct
timestamp/midpoint books and aggregate fixed, zero-aligned 100-quote-price-unit bins before cropping; depth returns original
levels. No canonical artifacts are written.

`GET /api/catalog/orderbook/historical-scale/{path}` calibrates the same exact
provider/exchange/product filename across its monthly raw partitions. Sixteen
evenly spaced minute-grid timestamps per partition (including endpoints) form
a bounded deterministic sample; absent books are skipped. Pooled percentiles
of populated 100-unit bins supply P50, P90, P95, and P99 plus coverage and method
metadata. Empty bins are excluded. In-memory calibration is invalidated by
partition membership, modification time, or file size. Full stored history may
include dates later than a viewed historical window: this is descriptive
comparison, not a causal or prospective research signal.

Heatmap cells include `[snapshotIndex, priceBinIndex, totalSize, bidSize, askSize]`.
The side components sum the original levels within the same complete fixed
bin, before visible-range cropping, and sum to the total within floating-point
precision. Depth continues to expose intact provider price bands.
