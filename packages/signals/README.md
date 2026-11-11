# Signals

`packages/signals` owns the predictive-output layer of `quant-factory` — the third stage of the `data -> features -> signals -> strategies` production path. Runner-registered signal families read canonical parquet-backed inputs (feature panels under `db/features`, derived data under `db/data`), emit validated prediction frames, and persist append-only results under `db/signals` for strategies, the API, and the viz frontend.

It is responsible for:

- canonical signal-family discovery via `SignalRegistry.register(...)`
- the shared `SignalRunner` lifecycle (`load_data -> compute -> validate -> persist`)
- the prediction-frame contract and its validation
- append-only persistence through `PredictionStore` under `db/signals/<signal_id>/`
- lightweight per-family `_signal/` markdown memory

It does not own portfolio construction or weights (`packages/strategies`), reusable ML mechanics (`packages/platform/ml-engine`), or feature publication (`packages/features`).

Read [AGENTS.md](AGENTS.md) first for the normative rules. This README is the package canon: what the package is, what it owns, and why it is shaped this way.

## The Signal Model

A signal is the most decomposed predictive unit strategies consume: one family, one numeric `prediction` column, one meaning.

- `family` — the stable registered signal type, lowercase kebab-case, scope first then predictive meaning (`equities_value-spread`)
- `preset` — a runnable YAML configuration in `extensions/lib/<family>/presets/`; every active family has a registered `default_preset`
- `signal_id` — the persisted identity, set by the preset `name` field with the `<family>-<preset>` convention (`equities_value-spread-default`)

`output_type` (`regime`, `time_series`, ...) is a coarse runtime hint; the actual meaning of the `prediction` column comes from the family name, family docs, and run metadata.

A family follows the same surface convention as a `packages/strategies` family: `src/` core engine, `optimization/` version lifecycle (`vNNN/` trees carrying `SPEC.md`, `VERSION.toml`, and after a run `HYPOTHESIS_OUTCOME.md`; latest at `optimization/vNNN/`, sealed versions under `optimization/version/vNNN/`), `references/` read-only source material, `verification/` the validator-owned instrument, and `tests/` implementer-owned tests — plus the runtime surfaces `presets/` and `_signal/CHANGELOG.md`, the record of runner and preset changes. The rules are `AGENTS.md` §5–§6. Research versions write only under `db/research/signals/<family>/`; the append-only `db/signals` history belongs to the registered runner, and a sealed version reaches it only by an explicit operator action.

## Runtime Model

Discovery is code-first — no YAML catalogs, no lifecycle skill stacks:

`extensions/lib/<family>/src/<family_with_underscores>/runner.py` -> `bootstrap.py` import -> `SignalRegistry` -> `manifest.py` catalog -> `api.py` / `cli.py`. Roots beginning with `_` are skipped. `src/signals/__init__.py` mounts optional family source roots so installed families import as `signals.<module>`.

Execution follows one shared lifecycle in `SignalRunner`:

1. `load_data()` — canonical parquet-backed inputs from `db/` via shared config surfaces (`config.QUANT_DB_ROOT`); no live external APIs
2. `compute(data)` — the family's model/rule logic returns a prediction frame
3. validation — required `timestamp` + numeric non-null `prediction`; optional `asset`, `model_id`, `predicted_at`, `run_id`, `signal_name`; `(timestamp, asset)` rows unique; runs for `save=False` too
4. optional persistence — `PredictionStore.save(...)` appends to `db/signals/<signal_id>/`; dedup by timestamp keeps saves idempotent

Concrete runners are supplied by the optional extension overlay. Use `qf-signals list` to inspect
the families installed in the current checkout.

Point-in-time discipline: row `T` is known at `T`'s close, and the data layer stamps late sources at availability ([data README](../data/README.md)), so signals never shift and nothing downstream adds a source lag. A prediction labeled `T` uses only inputs labeled `T` or earlier; strategies own only the decision-to-execution lag (`ExecutionTiming`).

One module, one path: family modules keep a single execution purpose (`model.py` vs `model_alternate.py`), and `runner.py` calls the live path only.

## DB Contract

```text
db/signals/<signal_id>/
  predictions.parquet   # append-only prediction history (dedup by timestamp)
  latest.json           # most recent prediction metadata
  index.json            # signal metadata and date ranges
  runs.json             # per-run metadata by run_id
```

- Signals write only here, only through `PredictionStore` — never `db/data`, `db/features`, or `db/strategies`.
- `apps/api` serves this tree through its signals router, filtering discovery to active registered families when the registry resolves.
- `packages/strategies` consumes these frames through stable signal IDs.

## Validation

`uv run qf-signals validate` machine-enforces catalog/registry/disk coherence for every entry: required registry metadata fields, kebab-case naming, docs and presets present on disk under canonical `extensions/lib/` roots, a valid registered `default_preset`, per-preset YAML `name`/`signal_type` coherence, a `tests/` directory, bootstrap import equal to the expected active set, and runtime runner class/module matching the catalog. Missing `_signal/` memory files and stray package-local virtualenvs are warnings. An absent or empty overlay yields a valid empty catalog.

`uv run qf-signals smoke [<family>]` runs default presets with `save=False` and validates the resulting frames. Extension implementations may make this expensive, so the practical fast baseline is package tests + `list` + `validate`, reserving smoke for input or mechanism changes.

## Publication

`uv run qf-signals publish` is the registry-driven "run every active family with `save=True`" surface: selection comes from the catalog, so the core never names a family. `--signal-type` (repeatable) narrows the selection, `--preset` picks one preset for a single family, `--all-presets` runs every preset file in the family's `presets_dir`, `--db-root` overrides `QUANT_DB_ROOT`, `--dry-run` runs the identical path with `save=False`, and `--fail-fast` stops at the first failing runner instead of recording it and continuing. The exit code is 1 when any runner failed.

Every runner emits one JSON line to stdout and, unless `--dry-run` is set, the same line is appended to `<db_root>/signals/publish.jsonl`:

```json
{"at": "...", "signal_type": "...", "preset": "...", "signal_id": "...", "status": "ok",
 "rows": 500, "first_timestamp": "...", "last_timestamp": "...", "rows_before": 0,
 "rows_after": 500, "run_id": "run-...", "duration_s": 0.01, "error": null}
```

`rows_before`/`rows_after` are the history parquet lengths around the save, so the ledger shows what each publish actually added. The ledger is a plain file beside the signal directories; listing surfaces iterate directories only and ignore it. Dedup and overwrite semantics stay `PredictionStore`'s.

Gate reality: there is no signals boundary test and `just ci` does not run `packages/signals/tests/`. The persistence side is gated indirectly by `just test-contracts` and `just test-workflow` (`tests/contracts/test_prediction_store_contracts.py`, `tests/workflow/test_signal_to_backtest_workflow.py`), so the catalog/registry contract checks are local-only — run them yourself.

## Extension Inventory

Concrete family names, mechanisms, presets, research notes, and archive inventory belong only to
an installation's `extensions/` overlay. Package metadata describes the generic control plane
without identifying installed user code.

## Code Layout

The public package contains the generalized control plane under `src/signals`. Concrete families (installation-owned, plus the shipped `example`) live flat under `extensions/lib/<family>/`, are discovered directly from that checkout overlay, and are excluded from the public wheel and sdist.

`src/signals` control plane, grouped by role:

- Control plane: `api.py` (boundary-errored operator API), `cli.py`, `manifest.py` (registry-derived in-memory catalog), `bootstrap.py`, `registry.py`
- Execution: `runner.py` (`SignalRunner`, `SignalRunConfig`, `SignalRunResult`), `contracts.py` (prediction-frame validation), `validators.py` (catalog validation + smoke), `metadata.py`, `naming.py`, `ids.py`

`extensions/lib/<family>/` shape: `src/<family_with_underscores>/` (`runner.py` is the only discovery target), `presets/` (`default.yaml` required), `tests/`, `optimization/`, `references/`, `verification/`, `_signal/`, local `README.md` and `AGENTS.md`. Directories beginning with `_` are hidden from discovery.

## Commands

```bash
uv run qf-signals list
uv run qf-signals validate
uv run qf-signals smoke [<family>]
uv run qf-signals publish [--signal-type <family>] [--all-presets] [--db-root PATH] [--dry-run]
uv run pytest packages/signals/tests -q
uv run pytest packages/signals/extensions/lib/<family>/tests -q
```

A family's optional `extensions/lib/<family>/requirements.txt` records which third-party libraries it imports.
It installs nothing: add each library to the workspace with `uv add --package <member>` and `uv sync`.
They never belong in the public wheel metadata.

## Docs

- [AGENTS.md](AGENTS.md): canonical package rules
