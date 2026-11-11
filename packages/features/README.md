# Features

`packages/features` owns the feature layer of `quant-factory`: it turns reusable data products from `packages/data` into model-ready feature datasets, and publishes them to `db/features`.

`src/features` is the publication control plane only: the explicit family catalog, validation,
smoke checks, and canonical publication to `db/features`. Everything that evaluates features
(IC analysis, diagnostics, selection, factor libraries) lives in an extension package so it never
ships with the core.

Read [AGENTS.md](AGENTS.md) first for the normative agent rules. This README is the package canon: what the package is, what it owns, and why it is shaped this way.

## The Feature Contract

A feature is data arranged for modeling. The lake-side placement test (full version in `packages/data/README.md`) routes two kinds of columns here:

- anything that uses another day's data with a **tunable window** — z-scores, changes, lags, momentum, any trailing-Nd ladder
- anything that **positions an asset** against other assets, a model, or a target — ranks, percentiles, relative context, interactions, labels

Feature families own these model-ready mutations: temporal windows, lags, rolling z-scores, cross-sectional ranks/percentiles, relative context interactions, labels, and family-specific transforms.

### Full panels and selection

Every family maintains a canonical full feature panel: the **marble slab** from
which smaller feature sets are sculpted. It contains the complete implemented,
defensible design space, including derived facts, indicators, temporal windows,
cross-sectional measures, and interactions. Correlated features remain available
until selection; correctness and explicit coverage are required from the start.

The family's config field defaults are its full panel, which is what a run builds when
no preset is named; the family documents its blocks and exclusions. Variant panels
change what is computed; consumers select columns. Selection
does not narrow the source panel or prevent it from growing. Window definitions
remain explicit and finite; completeness does not require arbitrary parameter
combinations. Legacy version names such as `v0` do not define the design boundary.

### As-of contract (point-in-time)

Inputs are stamped at availability by the data layer (`packages/data/README.md`): row `T` is what was known at `T`'s close. A feature for `T` uses only rows dated `T` or earlier, and this layer adds **no lag**; neither do signals or strategies. A source that publishes late is fixed by its stamp in the data layer, not by a downstream shift. Family-specific reporting clocks are noted in the family's `AGENTS.md`.

### Input boundary

- Feature families consume **data-derived products** as their input boundary.
- Never publish raw provider pass-through aliases, and never rebuild reusable derived logic inside a family — same-day reusable calculations move upstream to `packages/data`.
- Families **may** republish same-day derived columns as context. Pass-through of derived context is sanctioned; pass-through of raw is not.

### Publication shape

- Published datasets are **latest-state only**: no `vN/` directories, no `latest` symlinks. The code defines the current feature set.
- Features publishes; consumers select. A preset only changes what is computed and publishes its own panel; never publish a column subset of a full panel.
- Canonical frames require `timestamp`, require `asset` only for asset-panel families, and require numeric non-index columns.

## Control Plane

`features.api.PUBLISHABLE_FAMILIES` -> family runner -> `features.publication` -> `db/features/<resolution>/<category>/{data.parquet,meta.yaml}`.

Catalog entries may declare `presets_dir` for read-only introspection of variant
panels. `features.api.list_feature_presets(category)` reads only registered
top-level YAML definitions for that category; it does not import or execute a
producer. Browser statistics always describe the actual published file.

- Family discovery is explicit: each family's `runner.py` registers with `@FeatureRegistry.register(...)`, and bootstrap merges the registered families into `PUBLISHABLE_FAMILIES`. No YAML manifests for discovery.
- The public core remains importable with no extension overlay; in that state the catalog is empty and validation and CLI help remain valid.
- Runs are non-persistent by default: running a family computes features without writing canonical outputs. Publication is an explicit step.
- `uv run qf-features validate` checks that every declared runner and its full panel still import and instantiate.



## Family Folder Contract

Concrete families live under `extensions/lib/<family>`:

- `README.md`: trading/data purpose only
- `AGENTS.md`: feature-set-specific gotchas only (as-of clocks, slice boundaries, conventions)
- `presets/`: optional variant panels (the full panel lives in `config.py`)
- `docs/CHANGELOG.md`: dated, append-only change history
- `docs/PIPELINES.md`: concise upstream `packages/data` pipeline map
- `docs/FEATURE_REFERENCE.md`: tracked generated column reference for the current published dataset
- `output/`: generated audit and selection artifacts
- `src/<modules>/`: family code, slice-organized as needed

No `_feature/` folders, no feature YAML catalogs, no selected-feature-set JSON catalogs, no family version directories.

The core bootstrap deterministically mounts each installed `extensions/lib/<family>/src` directory so logical family imports remain stable in integrated development. Public wheels and source distributions contain only `src/features` and core tests/docs, never the extension overlay.

## Research Engine

Feature evaluation (leakage diagnostics, cross-sectional IC, selection, transform and factor
primitives, and analysis artifacts under `db/features/_analysis`) is installation-specific and
belongs in an optional extension package with its own CLI and README, never in the core.

Family-local experimentation belongs in `extensions/lib/<family>`, not the shared control plane. Promote publication mechanics into `src/features/*` only after reuse is proven and semantics are stable.

## Commands

```bash
uv run qf-features list
uv run qf-features validate
uv run qf-features smoke
uv run qf-features publish <category> --resolution <resolution> --force
uv run pytest packages/features/tests -q
```

Families register their runners with `@FeatureRegistry.register("<category>", ...)` in
`extensions/lib/<family>/src/<package>/runner.py` (the platform `family_registry`, as in signals and
strategies). Dependencies a family needs beyond the core belong to the installation that adds the
family, never in the public wheel.

## Docs

- Cross-sectional data-injection guidance is owned by the extension that provides it.
- Extension-owned working notes and research writeups live with their family.

For the lake-side half of the contract — raw vs derived vs feature, the vocabulary exception, and the point-in-time law — read `packages/data/README.md`.
