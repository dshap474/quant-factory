# ml-engine architecture

## Purpose and boundary

`ml-engine` is the reusable training-and-inference lifecycle for tabular
supervised prediction. A caller supplies a `pandas.DataFrame` and an explicit
`TrainingConfig`; the engine returns a complete in-memory `TrainingResult`.
Model persistence is explicit: callers either invoke `TrainingResult.save(path)`
directly or attach a `TrainingRun` callback that delegates the optional inference
artifact to the same save method. Status tracking is always on: every
`TrainingPipeline.run()` writes one live JSON sidecar — through the caller's
explicit `TrainingRun` when one is active, otherwise through a best-effort
implicit run resolved from the environment (see the README run-tracking
contract). Sidecar failures warn, are recorded on `TrainingResult.warnings`,
and do not fail training.

The package is deliberately not a financial or deployment system. It does not
construct targets, define feature families, store signal history, rank
portfolios, estimate covariance, calculate returns or P&L, manage registries,
or control promotion and deployment.

## Package ownership

```text
ml_engine
├── training
│   ├── configuration and schema validation
│   ├── methodologies
│   │   ├── walk-forward: expanding, rolling, purged, and embargoed folds
│   │   ├── holdout: one chronological train/test split
│   │   └── full fit: chosen estimators trained on every labeled row, with in-memory predict
│   ├── fold-local preprocessing and optional feature selection
│   ├── sklearn-compatible candidate fitting and OOS predictions
│   ├── generic metrics, deterministic selection, and cross-fitted ensembles
│   ├── final refit and TrainingResult
│   ├── optional immutable TrainingProgress callbacks
│   ├── always-on atomic TrainingRun status sidecars
│   └── atomic, checksummed artifact serialization
└── inference
    ├── manifest/schema/checksum validation
    ├── fitted preprocessing and model loading
    └── read-only row-aligned PredictionResult generation
```

The root package exports only version metadata. Consumers import runtime APIs
from the two explicit subpackages; no compatibility re-exports or quant-factory
imports are required.

## Training flow

1. Validate the flat configuration and required input columns.
2. Assign stable row identities, normalize timestamps to UTC, sort rows, and
   enforce the optional training cutoff.
3. Select the explicit holdout or walk-forward methodology and materialize one
   immutable fold plan. Every candidate receives the same row assignments.
4. Use the full-fit methodology on each candidate's selected fold training rows
   with fresh preprocessing and a cloned estimator, then call `FullFitResult.predict`
   for row-aligned out-of-sample predictions. Target and score-only eligibility
   masks are shared across candidates.
5. Compute configured metrics from OOS predictions only, apply eligibility
   gates, and select candidates with deterministic tie-breaks.
6. If requested, evaluate learned ensemble weights through chronological
   meta-cross-fitting; never report combiner in-sample performance as OOS.
7. Use the full-fit methodology to train selected estimators and preprocessing
   through the cutoff, then fit the final ensemble/transform from eligible
   training evidence.
8. Return the complete `TrainingResult` and its in-memory inference pipeline.

When supplied, the progress callback receives immutable values at validation,
planning, candidate-fold, evaluation, selection, ensemble, and final-refit
boundaries. Callback omission preserves the original write-free execution path.
Callback failures propagate because a tracked run must not continue when its
required status cannot be recorded.

For purged walk-forward plans, the first evaluation boundary is the earliest
boundary that retains `min_train_periods` usable periods after both the explicit
pre-evaluation gap and exact label-interval purging. Later boundaries advance by
the configured step and recheck the same invariant. The planner fails closed when
no complete evaluation window can satisfy it.

Unknown targets can remain in the normalized input for later inference but are
excluded from fitting and evaluation. Input order is not an implicit time
contract, and `entity_col` does not silently create one model per entity.

## Inference flow

`InferencePipeline.load(path, trusted=True)` validates the artifact manifest, compatibility
policy, declared files, and SHA-256 checksums before loading serialized state.
`predict(new_data)` validates required columns and dtypes, preserves caller row
identity and order, applies persisted feature ordering and preprocessing, runs
the fitted base estimators using each candidate's declared task (falling back to
the global task when no override is declared) and optional ensemble, then applies the persisted
prediction transform. It never fits, updates, selects, registers, promotes,
or persists predictions.

Joblib files are trusted-code artifacts and may execute serialized Python while
loading. Operators must load only artifacts from trusted sources. Checksums do
not authenticate who produced an artifact.

Prediction transforms are fixed, transform-only objects. Training rejects any
object exposing `fit()` because learning a transform would require its own OOS
fitting protocol; callers must complete that protocol outside this package or
provide a non-fittable deterministic transform. Transform-only objects need no
JSON serialization hooks: the artifact stores the object in Joblib and records
its class and state-file reference when richer config metadata is unavailable.

## Artifact spine

The saved pipeline is one versioned directory, written through a sibling
temporary directory and atomically renamed into place:

```text
model-v1/
├── manifest.json
├── config.json
├── schema.json
├── preprocessing.joblib
├── models/<candidate-name>.joblib
├── ensemble.joblib                 # when configured
├── prediction_transform.joblib     # when configured
├── oos_predictions.parquet
├── metrics.json
├── selection.json
└── checksums.json
```

`manifest.json` records artifact/package versions, task and selected candidates,
cutoff and data bounds, ordered required inputs, declared paths, dependency
versions, and a deterministic configuration fingerprint. `schema.json` is the
single source of truth for feature order, numeric dtypes, and identity columns; no
legacy schema aliases are accepted. `checksums.json`
contains SHA-256 values for every declared file except itself. Missing,
undeclared-critical, or mismatched files fail before deserialization.

## Tracked-run spine

`TrainingRun` owns one caller-selected root and stable run ID:

```text
<root>/
├── <run-id>.json   # atomically replaced mutable status
└── <run-id>/       # optional immutable artifact in the format above
```

The sidecar is a sibling so live updates never alter artifact manifests or
checksums. `TrainingRun.save(result)` first reports `artifact_save`, calls the
existing `TrainingResult.save(<root>/<run-id>)`, and marks `inference_ready=true`
only after that atomic save succeeds. A successful `final_refit=False` run has no
artifact directory. Exceptions escaping the context are recorded by type and
message without a traceback and still propagate. Abrupt process death leaves the
last honest `running` state; there is no heartbeat, reconciliation daemon, event
log, registry, or process-control layer.

The engine remains domain-neutral. It never chooses a repository DB root or stores
reverse links to consumer artifacts; callers pass the root and retain their own
run-ID provenance.

## Numerical verification boundary

The test suite checks the mathematical contracts through production entry points:

- split tests use hand-calculated chronological folds and assert purge, embargo,
  row-identity, and no-overlap invariants;
- metric tests use known-answer losses and correlations, including per-period and
  per-fold aggregation;
- ensemble tests assert aligned OOS rows, simplex weights, missing-value
  renormalization, and chronological meta-cross-fitting;
- training/inference round trips assert identical in-memory and saved predictions.

These finite tests cover the supported tabular contracts and adversarial boundary
cases; they are evidence of implementation correctness, not a proof for every
possible dataset or third-party estimator.

## Dependency and migration boundary

The base distribution requires Python 3.11+ (tested on 3.12) and depends on NumPy, pandas, PyArrow,
scikit-learn, and joblib. LightGBM and XGBoost are optional extras. The package
must remain importable without quant-factory and must not know its repository layout.
Consumers own domain-specific target construction and persistence.
