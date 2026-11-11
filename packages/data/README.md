# Data

`packages/data` owns the upstream data lake for `quant-factory`: canonical provider landings, reusable derived market data products, lake/schema validation, and the read-only parquet query surface.

It is responsible for:

- landing provider data into `db/data/raw`
- materializing reusable calculated market data into `db/data/derived`
- validating lake contracts and schema state
- exposing one dataset-oriented write runtime through `data.api`
- exposing read-only parquet queries through `data.query`
- hosting the feature-store storage mechanics that `packages/features` publishes through

It does not own signal-ready feature assembly. That belongs to `packages/features`; see the Lake Contract below for the exact boundary.

Read [AGENTS.md](AGENTS.md) first for the normative agent rules. This README is the package canon: what the package is, what it owns, and why it is shaped this way.

## Lake Contract

The lake has three layers, plus a corrected mirror of raw. This package owns raw, corrected and derived; `packages/features` owns the third.

| Layer | Path | Definition | Owner |
| --- | --- | --- | --- |
| raw | `db/data/raw` | Untouched provider/source truth. Provider-shaped layout, provenance-first. No computation beyond landing mechanics (typing, dedup, merge keys). | `packages/data` |
| corrected | `db/data/corrected` | A raw dataset with known provider faults held back or repaired. Same path, keys and columns as the raw dataset it mirrors, plus one `<field>_<rule>` flag column per correction. A corrected value uses only raw rows dated on or before its own row, so it never sees the future. No new facts. Raw is never rewritten. Readers of a corrected field read the mirror. | `packages/data` |
| derived | `db/data/derived` | Reusable facts computed from raw about one entity on one day. Canonical keys, normalized fields, aggregates, ratios, coverage and validity diagnostics. No tunable windows, no cross-asset positioning, no model or target awareness. | `packages/data` |
| features | `db/features` | Data arranged for modeling: tunable temporal windows, cross-sectional positioning, relative/interaction context, labels. Horizon-specialized presets bind windows to prediction horizons. | `packages/features` |

### The placement test

Ask in order:

1. **Is it untouched provider output?** → **raw**. **Is it that output with a provider fault held or repaired, using no later rows?** → **corrected**.
2. **Does it use another day's data with a tunable window?** Z-scores, changes, lags, momentum, any trailing-Nd ladder → **feature**.
3. **Does it position the asset against other assets, a model, or a target?** Ranks, percentiles, relative-to-BTC, interactions, labels → **feature**.
4. **Otherwise** → **derived**.

Worked examples:

- venue-aggregated close, futures/spot volume share, OI-to-volume, buy/sell imbalance, venue concentration → **derived** (same-day facts about one asset/date)
- market breadth, total market volume, BTC dominance → **derived** (same-day facts about the composite entity "the market")
- rolling 30d z-score, 7d change, cross-sectional momentum rank, BTC-relative return, forward-return label → **feature**
- exchange-reported funding rate exactly as the provider sent it → **raw**

### The vocabulary exception

The only temporal computation allowed in derived: an indicator may use past data iff

- its parameters are frozen by industry convention (RSI-14, MACD 12-26-9, ATR-14),
- the set is closed — it never grows window ladders, and
- reuse across multiple downstream consumers is proven.

A fixed-window technical-indicator table is the typical exception. The urge to add a second window variant of anything is the proof that it is a search space, not vocabulary — it belongs in features.

Any further exception is equally narrow: a fixed-window metric may live in
derived data only when its window is part of the metric definition. Alternate
windows, ladders, z-scores, ranks, and model-specific variants remain features.

### The point-in-time law

Row `T` is available at the end of day `T` (`T`'s close, UTC). If a source really arrives later, its dataset is stamped with the day it became available and keeps the provider's own date as a separate column (a filing is stamped with its filed date and keeps its period end). That choice is made once, here, and written in the source's README. No other layer adds a source lag: features, signals and strategies read row `T` as known at `T`'s close.

If it has a tunable window and it is in derived, it is misfiled. A lag applied anywhere but this stamping is a bug.

Rules at the boundary:

- Do not publish strict raw pass-through aliases in derived outputs (`raw_col -> prefixed_raw_col` copies). Raw values may be used internally; derived outputs expose computed products.
- Same-day cross-venue aggregation stays derived — better measurement of one fact, not positioning.
- Tunable-window and model-specific transforms never land under `db/data`. They belong in `packages/features`.

Sanctioned exceptions, so they don't read as rule violations:

- `canonical_feature` target: some control-plane flows materialize feature datasets through `data.api`'s feature-store machinery (`FeatureStore`, ...). This package hosts the storage mechanics; `packages/features` owns the published feature contracts.
- `db/data/raw/<resolution>/custom`: source-shaped landings that don't fit a provider directory. This covers both manually supplied files and automated pilot pipelines.

The feature-side half of this contract — what feature families may publish and the pass-through context rules — lives in `packages/features/README.md`.

### Delta tables

A dataset is stored either as loose parquet files or as a Delta table. A directory is a Delta table exactly when it holds `_delta_log/`; `data.platform.storage.delta_tables` is the only code that writes one.

- **Layout:** `<table>/_delta_log/` (the commit log, the source of rows, version and commit time), `<table>/_qf/` (sidecars: `layout.json` with partition, sort key and key columns; `meta.yaml`), and data files `<partition>=<value>/part-*.zstd.parquet` (or at the table root when unpartitioned). Only the log says which data files are live; never list or read them directly.
- **One dataset:** every walker (surface status, schema validation, the DB API index and browser, `data.query` collections) counts a table once as its directory and skips `_delta_log`/`_qf`. Freshness is the last commit time; a cache fingerprint is the table version.

## Runtime Model

One dataset control plane for writes, one query plane for reads.

### Writes: `data.api`

`DatasetSpec` -> `data.api` operation -> `DatasetHandlerRegistry` -> family handler -> `IngestResult`.

Sanctioned operations: `ingest_dataset`, `sync_dataset`, `materialize_dataset`, `validate_dataset`, `get_dataset_status`, `reconcile_dataset`.

```python
from data.api import DatasetKind, DatasetSpec, StorageTarget, sync_dataset

spec = DatasetSpec(
    dataset_id="example.prices.sync_1d",
    family="example",
    kind=DatasetKind.DATA_RAW,
    target=StorageTarget.CANONICAL_DATA_RAW,
)

result = sync_dataset(spec)
print(result.status, result.written_artifacts)
```

Target vocabulary: `canonical_data_raw`, `canonical_data_derived`, `canonical_feature`, `external`. Data package code never writes `db/signals` or `db/strategies`.

### Reads: `data.query`

Read-only queries over the canonical parquet lake, returning Polars frames. Single-file reads run as Polars lazy scans; multi-file collections and aggregations run on DuckDB. Callers use typed contracts instead of SQL:

```python
from data.query import ParquetQuery, query_parquet

result = query_parquet(
    ParquetQuery(
        scope="features",
        path="1d/example/data.parquet",
        columns=("timestamp", "close"),
        start="2024-01-01",
        time_column="timestamp",
        limit=10_000,
    )
)

df = result.frame
```

Supported scopes are `data`, `features`, `research`, `signals`, and `strategies`; `path` is relative to that scope under `QUANT_DB_ROOT`. `ParquetCollectionQuery` covers validated multi-file globs. A `path` that names a Delta table, or a legacy key mapped onto one, reads through the table's log. The source of truth stays parquet under `db/`; DuckDB is only the embedded execution engine.

Scope of use: the query plane is deliberately serving-shaped — bounded queries (default `limit` of 1000 rows), previews, stats, Arrow IPC export — for `apps/api`, notebook and research inspection, and multi-file collection scans. Production families in `features`/`signals`/`strategies` load their canonical inputs directly with Polars; `data.query` is not a modeling-input loader.

Keep the two planes distinct: `data.api` materializes and validates canonical datasets; `data.query` reads existing artifacts.

## Code Layout

The package has an explicit public-core/private-extension boundary:

- `src/data/` contains the generalized control plane, query plane, contracts, storage,
  schema, registry, and extension-loading mechanics. It imports and exposes without any
  installed extensions.
- `extensions/datasets/` contains concrete dataset families. The compatibility namespace
  preserves existing `data.features.<family>` imports.
- Provider clients live in `packages/platform/clients/<provider>-client/`; families import
  them directly (e.g. `from fred_client import FREDClientAdapter`).
- An installation may add companion surfaces beside `extensions/datasets/` (pipelines,
  native code, scripts, tests, docs).

Core never imports a named dataset or provider. Dataset services and operator metadata are
loaded deterministically from the optional extension roots; an absent or empty extension tree
produces valid empty catalogs.

The core dependency set is declared in `pyproject.toml`; the extensions' provider clients come
from the root uv workspace, so plain `uv run` has everything.

## Optional Extensions

Concrete dataset families and their operator assets are optional. With no `extensions/`
directory, the public package still imports, the generic query and schema surfaces work, and
the dataset and operator catalogs are empty. An installed overlay mounts family modules without
adding named implementations to public core.

An installation documents its own family inventory, provider notes, pipeline routing, and
operational examples inside its `extensions/` tree.

## Commands

```bash
uv run qf-data --help
uv run qf-data dataset --help
uv run qf-data schema-validate --mode warn
uv run qf-data schema-validate --mode warn --layer backups
uv run qf-data schema-validate --generate
uv run qf-data surface-validate
uv run qf-data surface-status
uv run qf-data surface-status --check
uv run qf-data surface-status --json
uv run pytest packages/data/tests -q
```

`surface-validate` checks the operator registry, registered scripts, and doc parity. `surface-status` reports the parquet footprint, the newest date inside the data (write/refresh stamp only where a surface has no date column or registers `freshness="write"`), cadence staleness, and quality issues (duplicate declared `keys`, future or pre-1900 dates, prices <= 0) of every registered db-writing pipeline, missing artifacts first, then stalest; `--check` exits non-zero when a daily/weekly pipeline is stale for its registry cadence or fails a check. A lake refresh should end with it. `schema-validate` keeps `db/SCHEMA.yaml` and per-layer schema files aligned with realized parquet.

For the normative agent rules, read [AGENTS.md](AGENTS.md). The DB-layer contract lives in the lake's `db/SCHEMA.yaml`.
