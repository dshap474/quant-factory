# Signal Rules

Signals turn prepared local data into predictions, not portfolio weights. The section outline
mirrors [the strategy rules](../strategies/AGENTS.md); signal-only law is §2 and §4.
Runtime documentation and commands live in [README.md](README.md).

## 1. Placement

- `src/signals/`: shared discovery, registry, runner, prediction validation, persistence,
  research-version discovery, the research surface, and evaluation helpers.
- `extensions/lib/<family>/`: family implementation, presets, tests, versions, references,
  verification, documentation, and `_signal/` production memory. Start a new family by copying an existing one and
  registering its runner `planned`, so it is never listed, smoked, or published until promoted.
- Family `optimization/vNNN/`: the latest version; older versions live in
  `optimization/version/vNNN/`. One directory per version.
- `db/research/signals/<family>/<version>/<experiment>/<run-id>/`: research runs.
- `db/signals/<signal_id>/`: production history, written only through `PredictionStore` by the
  registered runner.

A family holds `src/<family_with_underscores>/` (engine and the registered `runner.py`, §6),
`optimization/` (`DESIGN-SPACE.md` and versions), `presets/` (runnable YAML; an active family
needs `default.yaml`), `references/` and `verification/` (§6), `tests/`, `_signal/CHANGELOG.md`
(§3), an optional `requirements.txt` recording imports beyond the package `pyproject.toml` (a record only; install through
`uv add --package <member>`), and gitignored
`output/` scratch. The README orients and describes the current mechanism.

The module is conventionally the family directory name with hyphens as underscores (a name that
would clash across layers may take a suffix, as the shipped example's `example_signal` does);
discovery imports only the family's `src/<module>/runner.py`. Keep each module to one purpose and one execution
path: `runner.py` holds the live path only, and alternates get their own modules
(`model.py`, `model_alternate.py`), never branches on input shape.

## 2. Point-in-time predictions

Signals never shift. A prediction labeled `T` is computed only from input rows labeled `T` or
earlier, under the lake's point-in-time law (row `T` is known at `T`'s close; the data layer
stamps late sources at availability), and carries label `T` itself. No `shift`, lag, or as-of
adjustment of inputs or outputs at this layer, and nothing downstream applies a source-reporting
lag. Rolling statistics use prior windows, as in features; that is not a shift.

Each version names the feature columns it reads in its own code and reads only those, lazily.
Features never publish a subset for one consumer. A feature built inside a signal or strategy
moves into the owning feature family once a second consumer needs it.


## 3. Persistence and operating authority

Treat `db/` as read-only unless the operator requested the owning run or publication. Runners
default to production writes (`save=True`); experiments use `save=False` or a temporary `db_root`;
research rounds write only their run directory, never production history. Signals never write
`db/data`, `db/features`, or `db/strategies`, and never call live external data APIs.

Production history is append-only and gitignored. Never delete, rename, move, or prune
`db/signals/` directories, including those whose producers are archived. Column changes require a
deliberate history migration. After a backfill, rerun the latest period: `latest.json` reflects
the last save, not the maximum historical timestamp.

Every correctness-valid complete run is a research candidate, `SUPPORTED` or `FALSIFIED`. Metrics
grant no selection, promotion, registration, or activation authority; never choose by recency or
performance. Only the operator selects the working research baseline or promotes a sealed version,
by changing the registered runner or `presets/`, and records it in `_signal/CHANGELOG.md`; a
preset change is a production change.

## 4. Consumer contracts

Preserve consumed signal ids, column meanings, sign conventions, and cross-package APIs
(`PredictionStore`, `signals.api`, imported runners); change them only on operator direction.
Live-path families declare these frozen contracts in their `AGENTS.md`. Ids that strategies still read
are never deleted or renamed, even after their producer is gone.

## 5. Research runs and versions

Runs read prepared local data. Record each input by its path in the run's inputs JSON and read it
in place; never copy prepared data or a parent run's artifacts into a run folder, and never add
receipts, byte pins, hashes, or re-verifiers around recorded inputs. Relocation alone must not
invalidate a run. A run folder holds only what that run produced.

### Run outputs

A run saves only what the frontend, the version records, or the next version reads:

- per arm: `predictions.parquet` (the prediction-frame contract), evaluation tables as Parquet
  (IC series, quantile returns, hit rates) at the resolution the frontend charts, and
  `metrics.json`; `publish_research_surface` writes the tables and metrics once, under
  `surface/arms/<arm>/`;
- per run: small JSON records (outcome, comparisons, inputs used, integrity checks) and the
  published `surface/`; the version's `surface.json` selects it, and publication refuses a run
  folder over 1 GB.

Never persist model internals: per-refit fitted parameters, feature matrices, per-fold dumps, or
solver traces. Rebuild them with `rerun.py` and debug them in memory or in `.dev/`. Save each fact
once and nothing derivable from another saved file. A new artifact needs a named reader. A run
folder over 1 GB is wrong. Failed, blocked, or superseded attempts keep their outcome or blocker
JSON; their bulk is deleted once the version is recorded.

### Completing a version

Create a new version when prediction behavior or evaluation meaning changes, not for documentation
or behavior-preserving repairs, which stay in the existing unsealed version. Use the highest
existing version number + 1.

1. Read the design space and relevant references. Choose a question that reduces uncertainty.
2. Write and commit `SPEC.md` before implementation: hypothesis, input clocks (§2), arms and the
   unchanged control, evaluation window, metrics and decision criteria. This is preregistration.
   Record later corrections explicitly; do not rewrite the plan to fit results.
3. Make the smallest change that answers the question. Signal logic belongs in family `src/`
   (§6); arms and comparisons belong in `optimization/vNNN/`. `run.py` builds through
   `rerun.py` and the family runner.
4. Obtain independent implementation review. Commit the implementation before the run; the
   family, version and shared code it uses must have no uncommitted changes. Record that commit
   as `src_commit`.
5. Run the planned comparisons, including the unchanged control. If a run is blocked or invalid,
   record `NOT TESTED` and its blocker rather than inventing results.
6. Publish the accepted arms and the control to the research surface
   (`publish_research_surface`) and check them in the frontend. Negative results publish too.
7. Complete the version records, including `finding`, and reconcile the design space. Only then
   is the version recorded.

Do not add version-local engines, report renderers, launchers or verification frameworks. Do not
add configuration options for choices the experiment does not vary. Stop when the requested
comparison works and its checks and records are complete.

Sealed versions and their records are never silently overwritten; corrections use a clearly named
superseding record. Discover versions from `optimization/` records, not Git history.

### Design-space contract

Each family's `optimization/DESIGN-SPACE.md` is its research map: what the family has learned.
Read it before choosing experiments and update it as work progresses. The Viz Design Space view
renders it and links each deciding version to the Evolution view. Choose tests that most reduce
uncertainty about plausible signal designs, not only the largest immediate gain.

It has a short intro (scope, date and evidence boundaries) and exactly two sections:

- `## Dimensions`: one table, `| Dimension | Status | Current choice or what was ruled out |
  Deciding versions |`. Status starts with `locked` (the current choice, tested against
  alternatives), `closed` (ruled out at the tested settings, scope in the cell) or `open`
  (uncertain or untested); a short qualifier may follow, e.g. `locked (rule)`. Deciding
  versions are the family's `vNNN`, or ranges such as `v001–v003`.
- `## Open questions`: one table, `| Question | Evidence so far | What would distinguish the
  explanations |`, unranked, not an experiment queue.

Keep the map neutral: a failed configuration closes only that configuration, not the approach.
Keep one current state, replaced on each update; Git keeps earlier text. Do not repeat what
other sources own: each version's question, finding and status are its `VERSION.toml`, and
details are the version records. Recording a version is not done until its lineage fields and,
when a dimension's status changes, this map both reflect it. The conformance test checks the
shape and that every cited version exists.

Analyses run outside a version (read-only diagnostics, descriptive comparisons) are partial
evidence: name each in the intro with its date, sample and any choice made after seeing the
data, and cite it by that name. They add evidence to rows and open questions but never set
`locked` or `closed`, and cite no deciding version.

### Evolution

A family's history is its versions' `VERSION.toml` lineage fields, nothing else: `parent`,
`question`, `finding` and `status`. The Viz Evolution view reads them and draws each version
branching off its parent. Do not keep a separate evolution log.

### Version records

Each version produces:

- `SPEC.md`: hypothesis, the input clocks (§2), implementation and evaluation plan, before coding.
- `CHANGELOG.md`: the delta, reused components, and the experimental control.
- `REVIEW.md`: independent implementation review.
- `HYPOTHESIS_OUTCOME.md`: results, or `NOT TESTED` with the blocker.
- `VERSION.toml`, lowercase values from these lists:
  - `phase`: `preregistered`, `implemented`, `audited`, `run`, `recorded`;
  - `status`: `active`, `supported`, `falsified`, `inconclusive`, `descriptive`, `not_tested`;
  - `backtest_run_at` (UTC `"YYYY-MM-DDTHH:MM:SSZ"`, when the recorded run started; everything
    after it is forward) and `backtest_run_at_source` (`"run_id"`, or `"seal_commit"` /
    `"version_commit"` for backfilled versions);
  - `parent` (an existing `vNNN` of the family, or `"none"`) and `question` (one line), set at
    preregistration; `finding` (one line answering the question, leading with the verdict and
    key numbers), set when the version is recorded;
  - `run_id`, `[headline]` (`metric`, `control`, `candidate`, `difference`,
    `interval = [low, high]`), and `[checks]` (`name = true/false`). Family fields may follow;
  - `src_commit`, the full hash of the commit the recorded run executed
    (`git rev-parse HEAD` at run start, with family `src/` clean).
- `rerun.py`: `PRESETS` (runnable arms) and `build(preset)`, a `SignalRunner` on the newest inputs;
  the round's run builds through it so research and production share one path. A version that
  cannot rebuild sets `PRESETS = ()` and says why in its docstring. It runs against its own
  `src_commit` and need not load at HEAD.

Every active-family version has this shape, sealed ones included; a sealed version may gain only
these files, and a record written late is a stub that says so and links the evidence.
`tests/test_version_conformance.py` enforces the shape.

The family README orients; no goal docs, master docs, evolution logs or family changelogs beyond
`_signal/CHANGELOG.md`.

## 6. Family `src/` ownership and verification

Family `src/` holds the current signal implementation. A version may edit and refactor it within
its preregistered experiment; keep experiment-specific comparisons and records in the version
folder, and do not copy implementations into version folders to preserve history. Git and each
version's `src_commit` keep earlier code: do not keep retired implementations beside current code
so old versions import at HEAD; remove them as part of an authorized replacement.

`src/` is also production: in an active family a version's change must leave the `default`
preset's predictions unchanged, so new behavior enters through config keys the preset does not
set and goes live only when the operator changes the preset (§3). Changes to shared
`src/signals/` behavior need explicit operator approval, independent acceptance review and the
full package suite.

`references/` is operator-curated and read-only: fix the code or document the discrepancy; never
alter a reference to fit the implementation.

Only independent validators author or adopt `verification/` acceptance checks; each judges against
an oracle outside the implementation (reference known answers, a reference implementation, or the
published records), using small fixtures, never bulk run artifacts. Builders own `tests/` and
cannot promote their own checks into acceptance criteria. Keep sampled acceptance cases and raw
diffs out of implementer context; give root-cause directives instead.

Mathematical verification means the implementation matches its canonical references: check
provenance, units, signs, timing, and constraints, and test outputs against independently derived
known answers. At runtime, ordinary checks suffice: finite outputs, shared prediction validation,
and documented tolerances. Stronger runtime proofs need an explicit operator request.

## 7. Shared code

Every signal builds on `src/signals/` and the platform; use these, never a family copy:

- Runner: subclass `SignalRunner`, registered with `SignalRegistry.register(...)` in `runner.py`
  with `description`, `presets_dir`, `output_type`, `runner_module`, `default_preset`, and
  `status="active"`. The registered signal type is the family identity. No authored catalogs,
  package-local registry wrappers, or duplicate system docs.
- Output: prediction frames with `timestamp` and numeric non-null `prediction`; optional `asset`,
  `model_id`, `predicted_at`, `run_id`, `signal_name`; `(timestamp, asset)` unique when `asset`
  exists. Shared validation runs for `save=False` and saved runs alike.
- Persistence: `PredictionStore` only. Publication: `qf-signals publish`; research runs:
  `research_surface.publish_research_surface`.
- Training: platform `ml-engine` for all model training.
- Evaluation: `analysis_panel` and the shared signal-analysis tables; never add another IC, hit
  rate, or quantile-return implementation.
- Records: `VERSION.toml`, read by `research_versions.py`.

Keep private families and their dependencies out of public wheel and sdist metadata. Keep
mechanisms local until reused; when two versions or families need the same thing, ask the operator
to add it to `src/` rather than copying it.

## 8. Retiring and verification

Retire a family only on operator request, by deleting it: `git rm -r extensions/lib/<family>`.
Git keeps the code; note the date and the last commit that has it in the commit message. Its
`db/signals/` history stays put (§3). Restoring checks the family out of that commit. Afterwards
`qf-signals validate` passes and `qf-signals list` reflects the change.

Signal-system changes require package tests, `list` and `validate`, plus smoke checks when local
FeatureStore inputs exist, and any live-path verification the family declares.

## Related docs

- `README.md`: runtime documentation and command reference.
- Family work also reads the nearest family's `AGENTS.md`.
