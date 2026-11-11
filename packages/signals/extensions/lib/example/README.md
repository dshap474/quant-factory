# example

A reference scaffold for a from-scratch signal family: the canonical surfaces, what each one
holds, and — most importantly — who is allowed to write where. Copy this shape when starting a
new family. It is the signals counterpart of `packages/strategies/extensions/lib/_example` and
encodes the same structure (version lifecycle, family `src/` ownership, and checks kept apart
from the code they judge).

## Surfaces

| Surface          | Holds                                                            | Written by |
| ---------------- | ---------------------------------------------------------------- | ---------- |
| `src/`           | Core engine code: data loading, feature prep, model/rule mechanics, the registered `runner.py` | Family developers, with review |
| `optimization/`  | Version lifecycle: `vNNN/` trees (current at `vNNN/`, sealed under `version/vNNN/`), `DESIGN-SPACE.md` | One new version directory per experiment |
| `references/`    | Source material the signal replicates or designs against (books, papers, reference implementations) — read-only inputs | Maintainer |
| `verification/`  | The instrument: certification machinery, oracle kits, goldens, fixtures, evidence | Reviewers independent of the code under test |
| `tests/`         | Implementer-owned unit and integration tests                     | Family developers (a version's own tests live in its `vNNN/` tree) |
| `presets/`       | Runnable YAML presets; `default.yaml` names the production `signal_id` | Maintainer — a preset change is a production change |
| `_signal/`       | Lightweight memory of the registered production surface: `CHANGELOG.md` (production runner and preset changes) | Whoever changes the registered runner or presets |

The last two are signal-specific runtime surfaces: `qf-signals validate` requires `presets/`
for an active family and warns when `_signal/` memory is missing, so the scaffold carries both.

## Catalog discovery

A family enters the `qf-signals` catalog only through code: a module literally named
`runner.py` inside `src/<module>/` that calls `SignalRegistry.register(...)`.
There is no on-disk catalog file. This scaffold's `src/example_signal/runner.py` registers a
working runner (BTC 30-day momentum sign, optionally volatility-scaled) with `status="planned"`,
so `example` never appears in `qf-signals list` and is never smoked or published. When you copy
it into a real family, rename the family and module, rewrite `load_data`/`compute`, and register
with `presets_dir="extensions/lib/<family>/presets"` and `status="active"`: that is what brings the
family into existence for discovery, validation, smoke, and persistence.

## Production vs research

Two output roots, never confused:

- `db/signals/<signal_id>/` — append-only production history, written only by the registered
  runner through `PredictionStore`. The `signal_id` is the preset `name`
  (`<family>-<preset>`, here `example-default`).
- `db/research/signals/<family>/<version>/<experiment>/<run-id>/` — research artifacts of an
  optimization version. An experiment writes here and nowhere else; it never appends to `db/signals`.

A sealed `SUPPORTED` version does not become production by itself: only an explicit maintainer
action changes the registered runner or adds a preset, and that action is recorded in
`_signal/CHANGELOG.md`.

## Version history layout

The `optimization/` tree here shows the lifecycle shape with illustrative content (no run ever
happened): the current version lives directly at `optimization/vNNN/` (`v002/`, implemented),
and every sealed prior version lives unchanged under `optimization/version/vNNN/` (`v001/`,
recorded `not_tested`, with its `HYPOTHESIS_OUTCOME.md`). The version number is the highest
existing version + 1, bumped in the preregistration commit that freezes `SPEC.md`; `VERSION.toml`, `SPEC.md`, and `HYPOTHESIS_OUTCOME.md` tell one version's story. Every
SPEC states its input reporting clocks (AGENTS.md §2) and its named control. Sealed trees are immutable — a new
version is a new directory, never an edit.

The `tests/` vs `verification/` line is ownership, not test-kind: `tests/` is what a developer
uses while building; `verification/` holds the checks the code is judged by, and a change to the
family's code should not also change those checks.

## Verification

This scaffold ships `verification/` and `tests/` as empty layouts (see their READMEs); it has no
checks yet. When a family adds them, each check should cite its ground truth (a recorded
prediction frame, a known-answer computation from `references/`, or a reference implementation),
compare exactly unless recorded evidence licenses a relaxation, and prove itself by catching a
deliberately broken candidate. A check that fails is fixed against its ground truth, never
weakened to let a candidate pass.

## Lifecycle pointers

Normative rules live in `packages/signals/AGENTS.md` — read it in full before any work
here, including the family contract. Engine changes in
`src/` follow the family ownership rules. An experiment writes only its own `optimization/vNNN/` tree. Run artifacts publish to
`db/research/signals/example/`, never into this package and never into `db/signals/`.
