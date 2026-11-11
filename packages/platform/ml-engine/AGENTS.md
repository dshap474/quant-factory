# ml-engine agent guidance

This package is a domain-neutral Python distribution within the quant-factory workspace. Keep
changes focused on the requested behavior and preserve the package boundary:

- `ml_engine.training` owns configuration validation, chronological split planning,
  fold-local preprocessing, model fitting, out-of-sample evaluation,
  candidate selection, ensembling, final refits, and artifact creation.
- Shared interval arithmetic is delegated to public `signal_analysis.partitions`
  functions. Keep the public pandas interface and existing split behavior; the
  historical `embargo_periods` is a pre-evaluation gap, distinct from a post-test
  embargo. Do not duplicate that shared arithmetic in a private implementation.
- `ml_engine.inference` owns trusted artifact loading and read-only prediction.
- Financial targets, feature definitions, signal-history persistence,
  portfolio construction, backtesting, execution, registries, and deployment
  state belong to consumers, not this package.

The root `ml_engine` package exports version metadata only. Runtime classes are
imported from `ml_engine.training` and `ml_engine.inference`.

## Coding rules

- Keep execution paths explicit; do not add plugin registries, service
  containers, hidden dependency injection, or speculative abstractions.
- Preserve deterministic behavior and fail closed on schema, leakage, and
  artifact-integrity violations.
- Every code file starts with a purpose/docstring and usage example, then groups
  code under `# --------------------------------------------------------------------------- #`
  section banners. Keep the entry point last under its own banner.
- Use `pandas.DataFrame` at the public tabular boundary. Do not add a second
  dataframe framework without an approved contract.
- Do not serialize or load untrusted model artifacts in tests or tooling.

## Verification

Run the narrowest relevant tests while iterating. For training, splitting,
artifact, or inference changes, run the deterministic dummy-data smokes:

```bash
uv run pytest packages/platform/ml-engine/tests/smoke -q -W error
```

Before handoff, run the package quality gate from the repository root:

```bash
uv run ruff format --check packages/platform/ml-engine
uv run ruff check packages/platform/ml-engine
uv run ty check packages/platform/ml-engine/src
uv run python -m pytest packages/platform/ml-engine
```

Split changes must preserve both exact-purge and explicit fixed-gap workflows.
Artifact tests may load only artifacts they created locally in a temporary
directory and must pass `trusted=True` explicitly.

Use temporary output directories for build artifacts. Do not commit generated
models, coverage data, caches, or virtual environments.

## Pinned surfaces and tracking

- Never bump this package's major version (`pyproject.toml`) without operator
  direction: `_artifact_format.py` rejects artifacts across major versions,
  so a bump makes every stored model artifact in every sealed strategy
  version unloadable.
- Every `TrainingPipeline.run()` writes a `db/ml-engine` sidecar (gitignored,
  unrecoverable). Tracking failures warn and are copied onto
  `TrainingResult.warnings`; the fit still returns. A broken sidecar path
  still leaves no run record. Launch training with `ML_ENGINE_PRODUCER` set,
  or provenance lands as `unattributed/<script>`.
