# Strategies

`packages/strategies` owns the portfolio layer of `quant-factory` — the terminal stage of the `data -> features -> signals -> strategies` production path. Runner-registered strategy families load canonical parquet-backed inputs (feature panels and `db/signals` predictions), generate validated `StrategyWeights`, run them through the shared backtest engine, and persist version-first run artifacts under `db/strategies` for the viz frontend.

It is responsible for:

- canonical strategy-family discovery via `StrategyRegistry.register(...)`
- turning predictions and features into validated portfolio weight frames
- dispatching shared backtests through `packages/platform/backtest`
- saved research runs under `db/research/strategies/` and operator-promoted finals under `db/strategies/<family>/versions/`
- the strategy version memory model (`family -> memory_version -> preset -> run`)
- machine-checked coherence between registry, selected presets, version packs, and DB outputs

It does not own prediction generation (`packages/signals`) or reusable backtest engine mechanics (`packages/platform/backtest`).

Read [AGENTS.md](AGENTS.md) first for the normative agent rules. This README is the package canon: what the package is, what it owns, and why it is shaped this way.

## The Version Model

Strategy identity is hierarchical: `family -> memory_version -> preset -> run`.

- `family` — the stable registered strategy type, e.g. `example`
- `memory_version` — a mechanism boundary (`v001`, `v002`): cut a new version when target construction, feature interpretation, model family, portfolio construction, universe, or execution-timing semantics change; never for refactors or doc edits
- `preset` — a runnable parameter variant inside one memory version
- `run` — one execution of one preset under one memory version

Each memory version has at most one `final` artifact: a saved run the operator promotes explicitly (`finalize`). Nothing is selected by metrics, and a promoted final is never overwritten; record a correction explicitly.

Why this exists: strategies are mechanism-churn-heavy, and a backtest result is only meaningful relative to the exact mechanism that produced it. The version model keeps every run, preset, and artifact attributable to its mechanism. Presets are not globally valid — they live and die inside the memory version they were designed for.

The model is materialized through version-aligned ownership surfaces:

| Tree | Contents | Role |
| --- | --- | --- |
| `extensions/lib/<family>/optimization/vNNN/` | version code, configuration, hypothesis, outcome, specifications, verification, and frozen `presets/` | complete version record |
| `db/research/strategies/<family>/<vNNN>/<preset>/<run_id>/` | `decisions.parquet`, `backtest.parquet`, `meta.json`, `status.json` | saved runs (development evidence) |
| `db/strategies/<family>/versions/<vNNN>/final/` | a copy of the promoted run plus `selected_run_id` | canonical version output (lake side) |

A version number is assigned when its mechanism-changing hypothesis is frozen, not when it
is promoted. Rejected versions retain their code, memory, and research evidence but receive no
canonical `db/strategies` output.

The registered `default_preset` declares `memory_version` in its YAML and must have a
byte-identical frozen copy in that version pack, including archived version directories.
`align` and `validate` use this declaration; neither requires a master document. A
master declaration, where one exists, is a read-only fallback. Missing or
invalid active-version declarations fail validation; research recency never selects one.
The default catalog documentation link is the family README.

Package-level `extensions/lib/<family>/presets/*.yaml` are only the active version's runnable alias surface, not durable memory. An installation may add its own version-boundary and preset rules in an `extensions/AGENTS.md`.

## Runtime Model

Discovery is code-first — no YAML catalogs, no lifecycle skill stacks:

`extensions/lib/<family>/src/<package>/runner.py` -> `StrategyRegistry.populate()` -> `manifest.py` catalog -> `api.py` / `cli.py`. `StrategyRegistry` subclasses the shared `packages/platform/family-registry`. Families import by their bare package name. Directories beginning with `_` are skipped, runners loaded from `_archive/` or `optimization/version/` never register, and a second class cannot take a registered name.

Execution follows one shared lifecycle in `StrategyRunner`:

1. `load_data()` — canonical parquet-backed inputs from `db/` via shared config surfaces (`config.QUANT_DB_ROOT`); no live external APIs
2. `generate_weights()` — produce a `StrategyWeights` frame
3. `StrategyWeights.validate()` — wide frame indexed by `timestamp`, non-empty unique asset names distinct from `CASH`, unique sorted timestamps; complete target rows include `CASH` and sum to 1.0 within tolerance
4. shared backtest — dispatched to `packages/platform/backtest` (`run_backtest_from_strategy_weights`)
5. optional persistence — `decisions.parquet`, `backtest.parquet` and `meta.json` saved to the run directory

Concrete runners are supplied by the optional extension overlay. Use `qf-strategies list` to
inspect the families installed in the current checkout before invoking `run`.

`memory_version` is required for persisted runs; `save=False` smoke runs validate weights without writing.

Account-aware strategies call `decide(AccountState(...))` with current holdings,
cash, NAV and decision timestamp, and implement `ledger_inputs()`; the base `run()`
then drives them through `backtest.run_intent_ledger`. A null asset target means hold its actual
quantity; `CASH` is null whenever any target is null. Optional `quantity_limits`
align to the decision rows and assets. Each finite signed limit permits only a
same-sign reduction, intersected with the holding still present at execution;
zero forces flat and null imposes no limit. Limits are in asset quantity units,
not percentages, and take precedence over target weights for that instruction.
Optional `quantity_targets` (same alignment) request an absolute final held quantity
frozen at the decision: one risky asset, nonnegative, with a null weight target and
null `CASH` on that row and no numeric limit on that asset. Only the intent ledger
executes them (buys are clipped to fee-affordable cash); other adapters reject them.

Each row's timestamp is the decision time and its information cutoff.
`StrategyRunner.decide()` and `run()` stamp the typed `strategy_id` and `version`
(memory version) fields from the run configuration. `StrategyWeights.slice()` and
`StrategyWeights.concat()` split and join decision histories that share one contract.
Optional `observed_through` records, per row, the latest input time the decision saw;
each value is strictly before its row's timestamp.

`StrategyWeights.save()` and `from_parquet()` preserve targets, quantity limits, quantity targets,
execution timing, identity and JSON-native metadata in one Parquet artifact. Legacy plain
weight matrices still load with their legacy timing defaults. The explicit
shared `backtest.run_intent_ledger` path executes hold/limit instructions and
accepts canonical decisions from an account-aware callback or a saved artifact.
Ordinary backtest paths reject these instructions rather than dropping them.
An artifact records decisions for its declared account assumptions; changing
those assumptions requires regenerating account-dependent decisions.

## DB And Viz Contract

Performance `metrics_override` must contain both `strategy` and `benchmark`, each
with `total_return`, `sharpe`, `max_drawdown`, `ending_value`, `annualized_return`,
`annualized_volatility`, `calmar` and `positive_days`. All are finite numbers;
Sharpe, annualized return and Calmar may be null when undefined. `ending_value`
normalizes initial capital to $100; `positive_days` is a fraction. Supply values
under the experiment's documented return-window and statistical conventions.
Overrides are validated before publication writes; internal research names alone
do not satisfy the UI contract. The actual API response can also be checked with
`pnpm --dir apps/viz/web exec node scripts/check-research-surface.mjs <URL-or-JSON>`.

Research publishers may pass `asset_attribution` and `attribution_metadata` to
`publish_research_surface`. This optional daily table comes from the shared
backtest ledger's `collect_attribution=True` output, with a `config_id` column
added by the experiment. Metadata supplies initial capital, costs, configuration
labels and the selected configuration, plus an optional `capital_basis`:
`actual_holdings` (the default when absent) or `rebased_windows`, for experiments
that scale each later independently funded window's quantities and cash flows to
the compounded NAV at its start. The publisher validates and saves it in
the run's surface and declares `asset_attribution_v1` in the manifest. The
single-asset API reads that artifact directly; the frontend does not reconstruct
execution or funding. Existing publications without it retain legacy support.

```text
db/research/strategies/<family>/<memory_version>/<preset>/<run_id>/
  decisions.parquet   # StrategyWeights decision history
  backtest.parquet    # equity curve
  meta.json           # identity, config, data range, metrics
  status.json         # running/succeeded/failed, host, pid, phase timings, engine, lag_bars, error
db/strategies/<family>/versions/<memory_version>/final/
  ...                 # copy of the promoted run; meta adds selected_run_id
```

- `apps/api` serves both trees through `strategies.versioned` (`discover_strategy_versions`, `load_version_runs`, `load_version_final_artifact`); the viz frontend reads DB/API artifacts, never package files.
- A version appears in the frontend once it has a promoted `final/`; its saved runs are listed alongside.
- Archived families' exact outputs move to `db/strategies/_archive/<family>/` and stay out of default viz/API surfaces.

## Validation

`uv run qf-strategies validate` machine-enforces the control-plane contract:

- Hard errors: sealed-version isolation (no registered runner resolves into `optimization/version/`) and canonical preset durability (the registered `default_preset` matches its frozen copy under the active version pack byte-for-byte).
- Warnings: `db/strategies` version outputs whose `strategy_type` label does not match the producing family.

`uv run qf-strategies align <family>` checks one family's registry / registered preset / version / DB coherence. `just ci` gates these contracts through `tests/boundary/test_strategy_control_plane_boundary.py` in the boundary lane; the package-level `packages/strategies/tests/` suite is not part of that gate, so any new contract that must block a merge needs a boundary test too.

## Extension Inventory

Concrete family names, mechanisms, presets, research notes, and archive inventory belong only to
an installation's `extensions/` overlay. Package metadata describes the generic control plane
without identifying installed user code. Archived extension families remain cold,
undiscovered, unpackaged code; restoration is explicit and requires full validation.

## Code Layout

The public wheel contains only `src/strategies`. Installed extension families are importable by their bare package name
from `extensions/lib/<family>/src/<package>`; a family's optional
`extensions/lib/<family>/requirements.txt` records its extra dependencies but installs nothing; add each one to the
workspace with `uv add --package <member>` and `uv sync`.

`src/strategies` framework, grouped by role:

- Control plane: `api.py` (operator API: run, finalize, validate, smoke, scaffold), `cli.py`, `manifest.py`, `bootstrap.py`, `registry.py`
- Execution: `runner.py` (`StrategyRunner`, backtest dispatch), `weights.py` (`StrategyWeights`, `ExecutionMode`/`ExecutionTiming`), `results.py`, `contracts.py`, `ids.py`
- Versioned persistence: `versioned.py` (saved runs, `promote_run`, version discovery for the API/viz)
- Updated backtests: `backtest_updates.py` (started from the Viz Strategies → Backtesting tab's Update backtest button; reruns every `rerun.py` preset of one version through the newest inputs as a background job and writes `<version>/updated/<preset>.parquet` beside the published backtest, which it never changes; a version with a recorded commit always runs on that commit, one without in the current checkout)
- Coherence: `alignment.py` (preset-version alignment plus the align/validate checks)

`extensions/lib/<family>/` shape: `src/<module>/` (stable runtime, with `core/` when needed), optional
`optimization/<vNNN>/` version code and `scripts/`, and local `README.md`/`AGENTS.md`. Acceptance checks
live in `verification/`; `presets/` (active promoted aliases), `tests/`, `docs/`, `references/` and
`audit/` are optional (the shipped `_example` uses `verification/` and `references/`). Optimization notes and manual
workflow prompts stay under `optimization/`.

## Commands

```bash
uv run qf-strategies list
uv run qf-strategies families
uv run qf-strategies presets <family>
uv run qf-strategies validate          # machine-enforced contracts (`check` is an alias)
uv run qf-strategies align <family>
uv run qf-strategies smoke [<family>]
uv run qf-strategies run <family> --preset <preset> --memory-version <vNNN>
uv run qf-strategies finalize <family> --memory-version <vNNN> --run-id <run_id>
uv run pytest packages/strategies/tests -q
```


Python-only operator surface in `strategies.api`: `scaffold(...)`.

## Docs

- [AGENTS.md](AGENTS.md): normative strategy operator contract
