# packages/data — Rules

## Placement

- `src/data/`: generic dataset control plane, read-only queries, contracts,
  storage, schema, registry, and extension loading.
- `extensions/datasets/<family>/`: dataset implementations; `service.py`
  registers handlers and `repo.py` owns persistence.
- provider clients live in `packages/platform/clients/`, never here; optional
  `extensions/pipelines/{raw,corrected,derived}/` hold canonical writer wrappers
  when an installation adds them; other implementation utilities and assets stay
  under `extensions/`.
- `db/data/raw/`: provider truth; `db/data/corrected/`: raw mirrors with point-in-time
  fault corrections and flag columns (refresh order raw → corrected → derived; readers of a
  corrected field read the mirror); `db/data/derived/`: reusable computed market
  facts. Read [the Lake Contract](README.md#lake-contract) before placing
  data, including its temporal exceptions and point-in-time law. Tunable-window
  and model-specific products belong to `packages/features`.

## Boundaries

- Data work stays within `packages/data/` and `db/data/`. Dataset families never
  write `db/features`; only the hosted `FeatureStore` mechanics may do so for
  downstream callers. Never write `db/signals` or `db/strategies`, except schema
  regeneration explicitly authorized below.
- Canonical data writes use `DatasetSpec` through `data.api` and the family's
  `repo.py`; never bypass them with ad-hoc parquet writes. `data.query` remains
  read-only.
- New production series need a registered family and an automated pipeline wrapper for
  their layer; the public example family is run by hand. Never hand-seed a retired directory. Keep operator
  `primary_write_surface` metadata aligned with actual output paths so freshness
  monitoring observes the correct data.
- Preserve existing `data.features.<family>` exported names and their meaning;
  downstream consumers depend on them.

## Operating authority

- A lake refresh runs raw pipelines, then corrected, then derived (no features or signals).
  Check health with `uv run qf-data surface-status --check`.
- The lake and its local documentation, schemas, and registries are unversioned.
  Git cannot undo canonical writes; never delete `SCHEMA.yaml`
  files, or `REGISTRY.yaml` as cleanup.
- Schema repair must target only `data/raw` or `data/derived` using `--layer`.
  `schema-validate --generate` rewrites schemas across layers, including signals
  and strategies; use it only when the operator asks to refresh all layers.
- Validate changed operator surfaces with `surface-validate` and run targeted
  family/surface tests. Run the full core Data test suite when shared API,
  platform, or query code changes. Family `AGENTS.md` files and the docs below hold the
  operational commands and local guidance.

## Related docs

- `README.md`: lake contract, point-in-time law, runtime model.
- Live surfaces: `uv run qf-data surface-status` (freshness).
- CLI discovery and registry validation: `uv run qf-data --help`, `uv run qf-data surface-validate`.
- Family work also reads the nearest `extensions/datasets/<family>/AGENTS.md` or README.
