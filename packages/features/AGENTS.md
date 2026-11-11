# Features rules

Features turns derived data into broad, signal-ready panels. Follow the family
layout in [README.md](README.md) and read the owning family's `AGENTS.md` for
reporting clocks, variant panels, and upstream dependencies.

## Placement

- `src/features/`: the generalized publication control plane and its wiring only (catalog,
  registry, extension mount, publication, CLI). Evaluation, IC, selection and factor code
  are installation-specific and never live here.
- An installation's optional evaluation extension package under `extensions/`: IC analysis, diagnostics, selection, factor
  and transform libraries, and its CLI.
- `extensions/lib/<family>/`: family code, variant-panel presets, `tests/`, and
  documentation. Keep change history
  append-only. The package has `config.py` (its field defaults are the full panel;
  paths), `preset.py` only when the family has variant panels, `compute.py` (frame assembly, no side effects), `runner.py` (adapter to
  `features.publication`), and a narrow `__init__.py`.
- `db/features/`: canonical panels and analysis artifacts. Canonical panels use
  `features.publication` → `FeatureStore`; do not write them directly.
- `packages/data`: reusable derived inputs and same-day market-state calculations.
  Derived context may pass through; raw provider aliases may not.
- Features owns temporal transforms, ranks, relative context, interactions, and
  labels. Universe filtering, tradability, strategy selection, and column selection
  belong downstream. One exception: a family may drop assets that are not in its
  domain (for crypto, pegs, claims on another asset and index or ETF perps) through a
  reviewed list with evidence in the family package, applied before any feature is computed.

## Naming

One name per dataset, used for its folder, package, category and lake path:

- Category: `<domain>/<dataset>`, lowercase words joined by hyphens. The domain is
  the universe (`btc`, `crypto`, `equities`); a family's main panel may be the bare
  domain. Name datasets by content, never by resolution, panel shape, version, or
  person. A leading `cross_sectional/` or `index/` groups multi-asset panels; the catalog
  takes the domain from the part after it.
- Lake: `db/features/<resolution>/<category>/`. A category folder holds its full
  panel, one subfolder per variant panel, and the folders of its sub-categories
  (for a hypothetical `rates` family, `1d/rates/` would hold `base/`, `base-20d/`, and `calendar/`); `REGISTRY.yaml` says which is which.
- The full panel is not a preset. It is the family config's field defaults, built by
  `Runner.from_preset()` with no name, and it lands in the category folder itself.
  Variant-panel presets mirror the lake inside the family:
  `presets/<resolution>/<dataset path>/<name>.yaml`, with the domain implied by the
  family folder, landing in the `<name>/` subfolder (hypothetically `rates/presets/1d/base.yaml` →
  `db/features/1d/rates/base/`). A variant-panel preset pins every setting where it must
  differ from the full panel. One category may publish at several resolutions.
- The full panel holds every feature with its native windows and no horizon
  overlays. A horizon overlay (generic z/chg/lag operators tuned to one forecast
  horizon) is a preset in a subfolder named `<base>-<horizon>` (`base-20d`).
- Family folder: `extensions/lib/<domain>/`, holding one package,
  `src/<domain>_features/`. The package root is the domain's main panel; every other
  category is a subpackage named by its dataset with `-` replaced by `_`
  (hypothetically `rates/calendar` → `rates_features/calendar/`). Classes use the
  category words in CamelCase (`RatesCalendarRunner`).
- Uncategorized source logic shared by panels lives in `<domain>_features/blocks/` as
  plain compute modules: no config, preset, or runner. One block may feed panels at
  several resolutions.


## Data contracts

Inputs are stamped at availability (`packages/data/README.md`, point-in-time
law): row `T` is known at `T`'s close. A feature for `T` uses only rows dated `T`
or earlier and adds no source lag of its own. Historical references used to
calculate features are distinct from availability lags. Rolling statistics must
use prior windows, excluding the current observation.

Every feature family maintains a deterministic canonical full panel: the
"marble slab" containing its complete implemented, defensible feature design
space. Include supported derived facts, indicators, temporal transforms,
cross-sectional measures, and interactions before selection. Correlation or lack
of demonstrated predictive value is not a reason to omit an implemented feature
from the full panel. Correctness, defined units, provenance, and explicit
coverage remain requirements; fullness does not mean unbounded parameter sweeps.

The full panel is the family's built-in default: the config field defaults define
it, and omitted-preset CLI/API calls build it. There is no `default` preset file and
no alias for the full panel. Each family documents implemented blocks, upstream dependencies, and any
unsupported or unvalidated exclusions. Additions
enter the full panel. Selection happens downstream and never deletes from, or limits
growth of, the full panel. Keep existing consumer contracts
compatible and validate them when the full panel changes.

Features publishes; consumers select. A preset exists only when it changes what is
computed (universe, sources, parameters, horizon operators) and publishes its own
panel. Never publish a column subset of a full panel. Column choice, IC selection and
pruning belong to the consuming signal or strategy version, which names the columns
it reads in its own code and reads them lazily. Window definitions must be explicit;
canonical day/week/month/quarter/year anchors use 21 trading days per equity
month and 30 calendar days per 24/7 crypto month.

Discovery uses the explicit `features.api.PUBLISHABLE_FAMILIES` catalog; the code
defines the feature set. Do not add alternative discovery or feature-set catalogs.
Each published category holds current state; do not add per-run history
directories or `latest` symlinks.

## Operating authority

Feature work writes only within `packages/features/` and `db/features/`.
Computation does not imply publication. Before replacing an existing category,
identify and use its live producer from `meta.yaml` / `REGISTRY.yaml`;
do not assume the full panel produced it. Publish dependencies first.

Verify the resolved destination before publishing with a `db_root` override;
read-root overrides do not reliably control writes. Canonical outputs are ignored
and unversioned, so forced replacement can be unrecoverable. Never delete
`REGISTRY.yaml` or `meta.yaml` as cleanup.

Validate the family catalog and run tests for affected families. Shared-core
changes also require the full core test suite.

## Related docs

- `README.md`: control plane, publication shape, family folder contract.
- Family work also reads the nearest `extensions/lib/<family>/AGENTS.md` (reporting clocks,
  exclusions, family-specific gotchas).
