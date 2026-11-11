# ml-engine

`ml-engine` is a domain-neutral Python package for training and
serving leakage-safe tabular predictive pipelines. The deployable unit is the
complete fitted pipeline: preprocessing, estimators, ensemble state, and
prediction transforms are saved and loaded together.

The package is intentionally generic. It owns supervised regression and binary
classification mechanics, chronological validation, fold-local preprocessing,
out-of-sample evaluation, bounded candidate selection, ensembling, and trusted
artifact serialization. Financial targets, feature definitions, portfolio
construction, P&L, signal persistence, model registries, and deployment state
remain with the consuming application.

Shared label-end exclusion arithmetic is supplied by
[`quant-factory-signal-analysis`](../signal-analysis/README.md). The ML planner preserves
its pandas interface, chronological fold construction, and existing
`embargo_periods` pre-evaluation gap. Standalone research purged K-fold and a
post-test embargo are separately specified analysis operations; they do not
change this engine's training methodologies or artifact format.

The integrated dependency is tested on Python 3.12 and NumPy
1.26 (the workspace lock). Wider Python/NumPy combinations implied by minimum versions alone
are not an advertised tested environment for this integrated release.

## Install

```bash
# From the repository root (uv workspace member)
uv sync --frozen --group dev
```

Optional estimator integrations are available as extras:

```bash
uv sync --frozen --inexact --group dev --package ml-engine --extra lightgbm --extra xgboost
```

## Minimal API

The public runtime classes live under `ml_engine.training` and
`ml_engine.inference`; the root package exports version metadata only.

```python
from sklearn.linear_model import Ridge

from ml_engine.inference import InferencePipeline
from ml_engine.training import (
    CandidateConfig,
    MetricConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
    TrainingRun,
)

config = TrainingConfig(
    feature_cols=("feature_a", "feature_b"),
    target_col="target",
    timestamp_col="timestamp",
    split=SplitConfig(
        kind="expanding",
        min_train_periods=365,
        eval_periods=30,
        embargo_periods=7,
    ),
    candidates=(CandidateConfig(name="ridge", estimator=Ridge(alpha=1.0)),),
    metrics=(MetricConfig(name="rmse"),),
    selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
    random_seed=7,
)

with TrainingRun(output_root="./db/ml-engine", producer="example/v1") as run:
    result = TrainingPipeline(config).run(dataset, progress=run.update)
    run.save(result)

pipeline = InferencePipeline.load(run.artifact_path, trusted=True)
predictions = pipeline.predict(new_data)
```

## Training methodologies

Training methods are explicit modules rather than registry entries or subclasses:

```python
from ml_engine.training.methodologies import (
    build_holdout_plan,
    build_walk_forward_plan,
    fit_full_data,
)
```

- `build_walk_forward_plan` creates expanding, rolling, or purged chronological folds.
- `build_holdout_plan` creates one chronological train/test holdout.
- `fit_full_data` skips evaluation and fits chosen candidates on all labeled rows after
  they have already passed an external evaluation. Its in-memory `FullFitResult.predict(frame,
  candidate=...)` scores new rows through the fitted preprocessing (including its feature
  schema guard) and the shared task-aware prediction contract. `training_cutoff` and label
  maturity remain the caller's responsibility on this path.

The standard `TrainingPipeline` selects the appropriate fold methodology from
`SplitConfig` and uses `fit_full_data` for both candidate-fold fits and the final
selected-model refit, passing the selected training rows and each candidate's
feature subset and task. Training preprocessing uses `fit_transform` once per fit.

For every split, `min_train_periods` means usable training periods after all
exclusions. In a purged split, the default `purge_boundary="strict"` delays the
first evaluation window until that minimum remains after removing rows whose label
endpoint reaches the evaluation boundary (`target_end >= eval_start`). Set
`purge_boundary="closed"` to retain endpoints equal to that boundary and purge only
`target_end > eval_start`. A null `target_end` marks a permanently score-only row:
it is excluded from training and coverage counts but remains in evaluation windows.
`first_eval_period` can pin the zero-based first evaluation period instead of
searching by coverage; the planner rejects an unavailable boundary or insufficient
post-purge training coverage. `embargo_periods` remains a separate pre-evaluation
gap. Use exact `target_end` metadata with zero gap when it is available; otherwise
use a conservative gap at least as long as the known maximum label horizon. Feature
lookback is not a reason to add a split gap when features are computed causally.

`TrainingConfig.weight_col` passes finite, strictly positive training-row weights to
each fold fit and the final refit; score-only rows may leave it null. Set
`final_refit=False` for OOS-only research runs, in which case final models, inference,
and artifact saving are unavailable. Set `keep_fold_models=True` to retain fitted
estimators in `result.fold_models` and their fitted preprocessing in
`result.fold_preprocessors`, keyed by candidate and fold. It defaults to false to
preserve the normal memory profile. For predictions on raw pandas feature rows,
use `result.predict_fold(features, candidate="linear", fold=0)`: it applies that
fold's schema validation, learned preprocessing, and task-aware estimator scoring
without fitting. Scores follow `candidate_oos`, including binary-class probability
semantics, and preserve input row order. The method is available with
`final_refit=False` and does not apply final-refit ensembles or prediction transforms.
Raw retained estimators still support statistics such as tree importances; calling
their `predict()` directly bypasses preprocessing. Retained fold state remains
in memory and is not added to saved inference artifacts. Supplying rows to
`predict_fold` does not establish that they were held out of training.

Run tracking is always on: every `TrainingPipeline.run()` registers one JSON status
sidecar. `TrainingRun` is the filesystem observer — it atomically replaces the
sidecar and delegates artifact creation to the existing `TrainingResult.save()`
writer. Inside an explicit `TrainingRun` context (registered per-thread via a
contextvar; `current_training_run()` reads it) the caller's run owns the sidecar;
otherwise a best-effort implicit run is opened. Model artifacts are still written
only via an explicit `save`; a `final_refit=False` run completes without an
artifact and remains non-inference-ready. Inference is read-only: loading and
predicting do not fit, register, promote, or persist predictions.

Environment contract for implicit tracking:

- `ML_ENGINE_PRODUCER` — declared producer identity, conventionally
  `family/version` (e.g. `example-family/v001`); without it runs record
  `unattributed/<script-stem>`.
- `ML_ENGINE_OUTPUT_ROOT`, else `QUANT_DB_ROOT` + `/ml-engine`, else a cwd-walk to
  a directory containing both `db/` and `pyproject.toml` — resolves the run store.
- `ML_ENGINE_TRACKING=0` (or a pytest process) suppresses implicit sidecars;
  explicit `TrainingRun` contexts are caller-owned and always write.

Sidecar failures during an auto-tracked run warn (`RuntimeWarning`), are
appended to `TrainingResult.warnings`, and stop tracking rather than failing
training. Contextvar ownership does not cross
threads started with `ThreadPoolExecutor` or worker processes: fits dispatched to
workers each auto-register their own implicit sidecar. Sidecar readers that pin
`schema_version` strictly (for example the quant-factory db-api) must be restarted
after a sidecar schema change.

Tracked artifacts use one run-store root:

```text
<root>/<run-id>.json   # mutable atomic live status
<root>/<run-id>/       # optional immutable TrainingResult artifact
```

The package does not import repository configuration; the root comes from the
explicit `TrainingRun` argument or the environment contract above. Consumers may
persist the run ID in their own provenance records.

## Artifact safety

Artifacts contain joblib-serialized Python objects. `InferencePipeline.load()`
may execute serialized Python, so load artifacts only from trusted sources.
The loader verifies the manifest, declared files, checksums, schema, and
compatibility metadata before deserializing model state. Cross-major-version
portability is not promised. Checksums prove internal consistency, not origin;
shared or remote artifact stores still require an external provenance policy
such as signed manifests or immutable allowlisted roots.

## Package boundary

The v1 tabular boundary is `pandas.DataFrame`. Callers using another dataframe
library convert at that boundary. The package has no CLI, HTTP service,
database, scheduler, registry, optimizer service, or dependency on the
quant-factory repository. `TrainingRun` is a synchronous filesystem context, not a
service or process controller.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for ownership boundaries,
execution flow, and artifact layout.
