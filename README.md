# quant-factory

A package-shaped quant workspace for taking an idea from raw data to a backtested strategy, built to be extended safely by people and coding agents. It ships the framework and one complete worked example, with no market data and no strategies of its own.

## Quick Start

You need [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), Python 3.12, and, for the web app, [pnpm](https://pnpm.io/) with Node 22.13+ (not 23) or 24+.

```bash
uv sync --frozen --group dev
just ci     # the repository-wide local gate
just dev    # start the read-only web app and print its URL
```

Each layer has a CLI: `qf-data`, `qf-features`, `qf-signals`, `qf-strategies`, `qf-backtest` and `qf-production`, all run through `uv run`. `uv run qf-db-api` starts the HTTP API.

## The Example Chain

`db/` starts empty. The example populates it through every layer so you can see the contracts working. It needs network access and no credentials; prices come from Yahoo Finance.

| Layer | Family | Lives in | Output |
| --- | --- | --- | --- |
| data | `example.prices.sync_1d`, `example.prices.derived_1d` | `packages/data/extensions/datasets/example/` | `db/data/{raw,derived}/1d/example/prices/` |
| features | `example` | `packages/features/extensions/lib/example/` | `db/features/1d/example/` |
| signals | `example` | `packages/signals/extensions/lib/example/` | in-process predictions |
| strategies | `example` | `packages/strategies/extensions/lib/_example/` | `db/research/strategies/example/v002/` |

The data family lands daily bars for `BTC-USD`, `SPY`, `QQQ`, `GLD` and `TLT` and derives a `[timestamp, asset, close]` panel. The feature family adds `ret_1d` and `mom_30d`. The signal is BTC's 30-day momentum sign, optionally scaled by inverse volatility. The strategy compares an equal-weight book of the four ETFs against a capped momentum tilt. The signal and the strategy both read the feature panel; to stay small, the example strategy does not consume the example signal, where a production family would read published signals.

Run it in order. Each step reads an earlier layer's published parquet, never its Python:

```bash
# data: raw Yahoo bars, then the derived close panel
uv run qf-data dataset sync --spec-json '{"dataset_id":"example.prices.sync_1d","family":"example","kind":"data/raw","target":"canonical_data_raw"}'
uv run qf-data dataset sync --spec-json '{"dataset_id":"example.prices.derived_1d","family":"example","kind":"data/derived","target":"canonical_data_derived"}'

# features: close, ret_1d, mom_30d
uv run qf-features publish example    # add --force to republish

# signals: run the v002 preset in-process (nothing is persisted)
uv run python -c "
import runpy
rerun = runpy.run_path('packages/signals/extensions/lib/example/optimization/v002/rerun.py')
print(rerun['build']('default').run())
"

# strategies: both v002 arms through the backtest ledger, saved and judged against the SPEC
uv run python packages/strategies/extensions/lib/_example/optimization/v002/run.py
uv run pytest packages/strategies/extensions/lib/_example/verification -q
```

The strategy step prints a verdict against its written hypothesis. `FALSIFIED` is a valid result: the example demonstrates the process, not an edge.

Read the published output back through the query surface:

```python
from data.query import ParquetQuery, query_parquet

result = query_parquet(
    ParquetQuery(
        scope="features",
        path="1d/example/data.parquet",
        columns=("timestamp", "asset", "close", "mom_30d"),
        start="2024-01-01",
        time_column="timestamp",
        limit=10,
    )
)
print(result.frame)
```

## How It Fits Together

```text
data -> features -> signals -> strategies -> production -> execution
```

Research runs alongside this path and promotes validated work into it. The production and execution packages are a separate boundary: a tracked deployment definition is not proof that anything is live.

The lake under `db/` is the interface between layers:

1. **Writes flow one way.** A layer writes only its own `db/` surface.
2. **Reads are lake-only.** Downstream consumes published parquet, not upstream package internals.
3. **Data stamps availability.** Row `T` is what was known at `T`'s close, and a source that publishes late is stamped late. Nothing downstream adds a lag; a strategy decides on `T`'s close and fills on the next bar (the next close for the close-only example).

If a strategy needs an input that doesn't exist, build it upstream-first: land the raw data, derive the reusable product, publish the feature, then consume it.

| Location | Owns |
| --- | --- |
| `packages/data` | provider landings, reusable derived products, lake and schema validation, the `data.query` read surface |
| `packages/features` | signal-ready feature datasets |
| `packages/signals` | predictive signal families and persisted predictions |
| `packages/strategies` | strategy families, presets, runners and backtests |
| `packages/execution` | order intent, sizing, accounting and reconciliation contracts; venue adapters are extensions |
| `packages/production` | deployment contracts and validation; the scaffold has no active deployments |
| `packages/research` | source material, experiments and promotion candidates |
| `packages/platform` | shared backtest, ML, config, family discovery, signal analysis and provider clients |
| `apps/api`, `apps/viz` | read-only HTTP API and web UI over the lake |

Each package's `README.md` explains it in full, and its `AGENTS.md` holds the working rules for coding agents.

## The Lake

`db/` is git-ignored, so your data stays local; the repository tracks only the `.gitkeep` files that hold its empty skeleton. Set `QUANT_DB_ROOT` to keep it elsewhere.

```text
db/
├── data/
│   ├── raw/        # untouched provider landings
│   ├── corrected/  # raw mirrors with known provider faults repaired
│   └── derived/    # reusable same-day market data products
├── features/       # signal-ready datasets, latest state only
├── signals/        # append-only predictions
├── strategies/     # versioned, immutable run outputs
├── research/       # research-owned run artifacts
├── execution/      # execution journals and state
├── admin/          # operator bookkeeping
└── backups/        # local snapshots
```

To place a new column, apply these tests in order:

1. Untouched provider output? It is raw.
2. Uses another day's data with a tunable window (lag, rolling z-score, trailing change)? It is a feature.
3. Positions the asset against other assets, a model or a target (rank, percentile, interaction, label)? It is a feature.
4. Otherwise it is derived.

Canonical frozen-parameter indicators (RSI-14, MACD 12-26-9) and same-day facts about composite entities (market breadth, BTC dominance) may also live in derived. `packages/data/README.md` and `packages/features/README.md` have the full definitions.

## Add Your Own

Every pipeline package separates `src/`, the generalized core, from `extensions/`, where your families, venues and deployments go. The core works with `extensions/` absent and never imports a named extension.

To add a family, copy the matching example, rename it, rewrite its `load_data` and `compute` (or `generate_weights`), and register it `active`. The example signal is registered `planned` and the example strategy's folder starts with `_`, so neither appears in `qf-signals list` or `qf-strategies list`. Each example's `README.md` and `optimization/` tree show the version layout (`SPEC.md`, `VERSION.toml`, `rerun.py`) that real families follow.

Validate each layer as you go:

```bash
uv run qf-data schema-validate
uv run qf-features validate
uv run qf-signals validate
uv run qf-strategies validate
```

## Credentials

The example needs none. Provider clients under `packages/platform/clients` read keys from environment variables such as `FRED_API_KEY`. No client reads secrets from `.env` files; yf-client alone reads its non-secret `YF_*` settings from one.

## Contributing and License

See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed; see [LICENSE](LICENSE).
