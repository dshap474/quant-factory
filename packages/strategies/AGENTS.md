# Strategy Rules

The canonical shared strategy rules. Read them in full before strategy work, then the nearest family's
`AGENTS.md`.

## 1. Placement

- `src/strategies/`: shared runners, persistence, lifecycle, and research-surface contracts.
- `extensions/lib/<family>/`: family implementation, tests, versions, and documentation;
  `extensions/` itself holds only the shared extension docs, tests, and requirements.
- `extensions/templates/<template>/` (optional; none ship): copy-in template code. Never
  imported or registered; a family copies it into its own `src/` and owns the copy.
- Family `optimization/vNNN/`: the latest version; older versions live in
  `optimization/version/vNNN/`. One directory per version.
- `db/research/strategies/<family>/<vNNN>/<preset>/<run_id>/`: research runs; the
  version's `surface.json` selects its published surface.
- `db/strategies/<family>/versions/<memory_version>/`: separately promoted canonical outputs.
- `db/strategies/_archive/`: outputs of retired families (§7).
- `packages/research/`: literature and experiments without a strategy-family home.

## 2. Backtests and versioning

Backtests use prepared local data. Record each input by its path in the run's inputs JSON and
read it in place; never copy prepared data or a parent run's artifacts into a run folder, and
never add receipts, byte pins, hashes, fingerprints, or re-verifiers around recorded inputs or
outputs; Git holds the history. Relocation alone must not invalidate a run. A run folder holds
only what that run produced.

### Run outputs

A run saves only what the frontend, the version records, or the next version reads:

- per account: `decisions.parquet` (`StrategyWeights`), `backtest.parquet` (the daily NAV and
  return series), `meta.json` with the run metrics, and positions, trades, asset attribution or
  portfolio diagnostics when a family publishes them;
- per run: small JSON records (outcome, comparisons, inputs used, integrity checks) and the
  published `surface/`.
- per `StrategyRunner` saved run: `status.json` (state, host and pid, phase timings, engine, execution `lag_bars`,
  error), written when the run starts and rewritten when it ends; Viz Backtest Engine reads it. A
  failed run's folder holds only `status.json`.

Never persist policy internals: per-day state snapshots, per-asset record dumps, model,
scenario or covariance arrays, or solver traces. Rebuild them with `rerun.py` and debug them in
memory or in `.dev/`. Store tables as Parquet, not large JSON. Save each fact once and nothing
derivable from another saved file. Save diagnostics at the resolution the frontend charts. A new artifact needs a named reader. An account is
normally ~30 MB; `publish_research_surface` refuses a run folder over max(1 GiB, 48 MiB per
published account) — a grid counts its configurations, otherwise one account.

Failed, blocked, or superseded attempts keep their outcome or blocker JSON; their bulk is
deleted once the version is recorded. Only the published run keeps its account outputs.

### Completing a version

Use new versions for substantial changes in strategy approach or implementation. Within a
version, test worthwhile variants that share most of the code and are inexpensive to add or
run. Group related comparisons together rather than creating a version for each small tweak.
Plan comparisons before inspecting results, and report every outcome.

Documentation and behavior-preserving repairs do not require a new version. For a new version,
use the highest existing version number + 1.

For each version:

1. Read the design space and relevant references. Choose a question that reduces uncertainty.
2. Write and commit `SPEC.md` before implementation. Define the hypothesis, trading rules,
   controls, data window, fees and funding, metrics, and the pass rule (the family's selection
   standard unless the SPEC names another). This is preregistration. Record later corrections explicitly; do not rewrite the plan to fit results.
3. Make the smallest change that answers the question. Strategy logic belongs in family
   `src/`; experiment-specific arms and comparisons belong in `optimization/vNNN/`.
   `run.py` builds through `rerun.py` and the existing family runner.
4. Obtain independent implementation review and run the applicable existing checks. Commit
   the implementation before the backtest; the strategy, experiment and shared code used by
   the run must have no uncommitted changes. Record that commit as `src_commit`.
5. Always backtest the planned comparisons, including the unchanged control, fees and funding,
   even when activity, chart-review, source-fidelity or hypothesis criteria fail. Those failures
   are findings to report separately from returns; they do not block simulation or publication.
   Keep the frozen trading rules and thresholds. If data integrity or execution correctness
   prevents a valid account, record NOT TESTED for that account with the concrete blocker.
6. Publish all valid accounts and controls to the research surface. Check the charts,
   metrics, composition and applicable diagnostics in the frontend. Negative results publish too.
   Blocked versions must also appear in the strategy navigator, with NOT TESTED and their
   actual blocker in Overview, Composition and Portfolio diagnostics, plus current Details
   records. Verify the API and browser views after every run before reporting completion;
   a blocked backtest is not a reason to leave the frontend behind.
7. Complete the version records (§5), including `finding` in `VERSION.toml`, and reconcile
   the design space with the findings and remaining uncertainty. Only then is the version recorded.

Use existing runners, backtesting, metrics and publication tools. Do not add version-local
engines, report renderers or launchers. Do not add configuration
options for choices the experiment does not vary. Stop when the requested comparison works
and its required checks and records are complete.

Preserve records, not bulk: never silently overwrite Markdown or JSON records or the published
surface; record corrections explicitly. Discover versions from `optimization/` records, not
Git history. Git preserves their implementations.

## 3. Operating authority

Treat `db/` as read-only unless an operator-requested run or publication owns the write;
research writes stay in the run directory and its version pointer. Strategies never write
`db/data`, `db/features`, or `db/signals`.

Every valid complete run is a research candidate, regardless of its hypothesis status.
Metrics and rankings grant no selection, promotion, deployment, trading, or capital authority;
working-baseline selection and promotion require explicit operator action. Never choose a
surface by recency or performance.

## 4. Family `src/` ownership

Family `src/` contains the current strategy implementation. Research versions may edit and
refactor it within the authorized experiment. Keep experiment-specific comparisons and records
in the version folder. Reuse existing components; do not copy implementations into version
folders to preserve history. Git and each version's `src_commit` preserve earlier code.

Editing `src/` does not select a baseline, change a saved account, or authorize deployment or
trading. Current code and the selected baseline are separate: a selected baseline identifies
an explicitly chosen version and run, executed at its recorded commit (§6). Do not change preset
defaults or baseline pointers as a side effect of research.

`references/` is user-curated and read-only. Fix the code or document a discrepancy; never
alter a reference to fit an implementation.

### Review and checks

Run the applicable existing checks. Do not add tests unless the user requests them. Do not
rewrite acceptance checks to make an experiment pass or create a verification framework for
each version. Changes to shared engine behavior require explicit user approval, independent
acceptance review and the applicable full suite; ordinary family research is not an engine rewrite.

When new acceptance checks are requested, independent validators own `verification/`;
implementers do not edit it. Use expected answers derived independently
of the implementation, such as source examples or a reference implementation. Keep sampled
acceptance cases out of implementers' context; communicate the underlying defect instead.
Use small fixtures, not bulk run artifacts. Existing checks live in `verification/e2e/` and
one folder per source area; follow the layout of an existing family's `verification/`.
Do not reorganize a family's test layout as an incidental part of an experiment.

For mathematical changes, review source interpretation, units, signs, timing and constraints
against independent expected answers using existing checks where applicable. Recorded-output
end-to-end checks detect changes; they alone do not establish correctness. Report missing
independent coverage instead of inventing proof or bypassing a failed check. At runtime use
ordinary numerical checks: finite outputs, solver status and documented tolerances. Stronger
runtime proofs require an explicit user request.

## 5. Research documentation

### Design-space contract

Each strategy's `optimization/DESIGN-SPACE.md` is its research map: what the family has
learned. Read it before choosing experiments and update it as work progresses. The Viz Design
Space view renders it and links each deciding version to the Evolution view.

Choose tests that most reduce uncertainty about plausible strategy designs, rather
than only chasing the largest immediate performance gain.

Selecting a working baseline updates it, as a recorded version does: the intro and the rows
that quote the baseline's figures. It has a short intro (scope, date, the working baseline and
evidence boundaries) and exactly two sections:

- `## Dimensions`: one table, `| Dimension | Status | Current choice or what was ruled out |
  Deciding versions |`. Status starts with `locked` (the baseline's choice, tested against
  alternatives), `closed` (ruled out at the tested settings, scope in the cell) or `open`
  (uncertain or untested); a short qualifier may follow, e.g. `locked (weekly)`. Deciding
  versions are the family's `vNNN`, or ranges such as `v002–v004`.
- `## Open questions`: one table, `| Question | Evidence so far | What would distinguish the
  explanations |`, unranked, not an experiment queue.

Keep the map neutral: a failed configuration closes only that configuration, not the approach.
Keep one current state, replaced on each update; Git keeps earlier text. Do not repeat what
other sources own: the baseline's design is `docs/ARCHITECTURE.md`, each version's question,
finding, status and baseline selection are its `VERSION.toml`, and details are the version
records. Recording a version is not done until its lineage fields and, when a dimension's
status changes, this map both reflect it. The conformance test checks the shape and that
every cited version exists.

Analyses run outside a version (read-only diagnostics, descriptive comparisons) are partial
evidence: name each in the intro with its date, sample and any choice made after seeing the
data, and cite it by that name. They add evidence to rows and open questions but never set
`locked` or `closed`, and cite no deciding version.

### Evolution

A family's history is its versions' `VERSION.toml` lineage fields, nothing else: `parent`,
`question`, `finding`, `status` and `baseline_selected_at`. The Viz Evolution view reads them
(`records.family_versions`) and draws the baseline chain as the trunk with every other version
branching off its parent. Do not keep a separate evolution log.

### Architecture diagrams

A family with a selected baseline keeps `docs/ARCHITECTURE.md`, the architecture of that baseline
as Mermaid code; the Viz Architecture view renders it in the browser, so there are no generated
images. Its title is `# Architecture — baseline vNNN`, naming the version with the latest
`baseline_selected_at`. Each `## ` section is one diagram: one ```` ```mermaid ```` block,
then its notes. It starts with two sections: `## Pipeline` (inputs → forecast → sizing and
constraints → execution, with the decision and fill timing) and `## State` (what carries
from one decision to the next and what changes it; a stateless strategy says so). Two optional
sections may follow, in this order: `## Alpha model` and `## Risk model`, each the family's
current engine `src/` (which may be ahead of the baseline; the section says so) with its
settable slots. Other model detail goes in the notes, not extra diagrams. Selecting a new baseline updates this file in the
same change; the conformance test checks the title against the records.

### Version records

Each version produces:

- `SPEC.md`: hypothesis, implementation and evaluation plan, before coding.
- `CHANGELOG.md`: the delta, reused components, and the experimental control.
- `REVIEW.md`: independent implementation review.
- `HYPOTHESIS_OUTCOME.md`: results, or `NOT TESTED` with the blocker.
- `VERSION.toml`, lowercase values from these lists:
  - `phase`: `preregistered`, `implemented`, `audited`, `run`, `recorded`;
  - `status`: `active`, `supported`, `falsified`, `inconclusive`, `descriptive`, `not_tested`;
  - `backtest_run_at` (UTC `"YYYY-MM-DDTHH:MM:SSZ"`, when the recorded run started; the
    Viz Backtesting page lists it per version) and `backtest_run_at_source` (`"run_id"`, or `"seal_commit"` when the time is the sealing
    commit's);
  - `parent` (an existing `vNNN` of the family, or `"none"`) and `question` (one line),
    set at preregistration; `finding` (one line answering the question, leading with the
    verdict and key numbers, e.g. `"No: Sortino 1.20 vs 1.50, -0.30"`), set when the version
    is recorded; `baseline_selected_at` (UTC `"YYYY-MM-DDTHH:MM:SSZ"`), set only when the
    operator selects the version as the working baseline;
  - `run_id`,
    `[headline]` (`metric`, `control`, `candidate`, `difference`, `interval = [low, high]`),
    and `[checks]` (`name = true/false`). Family fields may follow;
  - `src_commit`, the full hash of the commit the recorded run executed
    (`git rev-parse HEAD` at run start, with family `src/` clean).
- `rerun.py`: `PRESETS` (tradable arms) and `build(preset)`, a `StrategyRunner` on the newest
  complete inputs; `run.py` builds through it so the backtest and its updates share one path.
  A version that cannot rebuild sets `PRESETS = ()` and says why in its docstring. `rerun.py`
  runs at its own `src_commit` (§6); it need not load at HEAD.

Every active-family version has this shape, recorded ones included. A recorded version may
receive missing required records or explicit corrections, but do not rewrite its implementation.
A record written late must say so and link the evidence.
`tests/test_version_conformance.py` enforces the shape.

The family README orients; no duplicate goal docs, master docs, evolution logs or family changelogs.
Runtime identity and `memory_version` belong in runner configuration.

## 6. Shared code

Every strategy builds on `src/strategies/` and the platform `backtest`; use these, never a
family copy:

- Runner: subclass `StrategyRunner` (`runner.py`), registered in `src/<package>/runner.py`.
  Implement `generate_weights` for a full weight history; `_decide_with_account_state` plus
  `ledger_inputs` when decisions depend on holdings (the base `run()` replays them through the
  shared intent ledger); or `run_nav` only for event-driven fills NAV weights can't express.
  Never write a family backtest loop.
- Output: `StrategyWeights` (`weights.py`) with `ExecutionTiming`, saved by `.save()` and
  checked by `validate_strategy_weights_contract`. Each row's timestamp is when it may act;
  `observed_through` records an earlier input cutoff; a null target holds the actual quantity
  and `quantity_limits` bound it. Consumers read only this artifact and market data; extend
  `weights.py` when a family can't express something.
- Inputs: consume data, features and signals as published: row `T` is known at `T`'s close
  (`packages/data/README.md`, point-in-time law). Never add a source-reporting lag in strategy
  code; if a source looks late, tell the operator, since the fix belongs in the data layer. The
  strategy owns only decision-to-execution timing: decide at `d`'s close and fill on the next bar
  (`d+1`'s open, or its close for close-only data), through `ExecutionTiming`.
- Feature columns: each version names the feature columns it reads in its own code and reads
  only those, lazily. Features never publish a subset for one consumer. A feature built inside a
  signal or strategy moves into the owning feature family once a second consumer needs it.
- Simulation: `backtest.run_backtest_from_strategy_weights` and `run_intent_ledger`.
- Metrics: `summarize_returns` and `backtest.path_metrics`, or the family's one existing
  ratio module; never add another Sharpe, Sortino, or drawdown implementation.
- Publication: `publish_research_surface`, which adds `signal_analysis.selection` statistics
  (`manifest["selection"]` and `selection_*` diagnostics) to every grid of two or more
  configurations; display only, never a selection or gate. Updated backtests: `rerun.py` via
  `strategies.backtest_updates` (Viz Strategies → Backtesting, Update backtest), written to
  `<version>/updated/` beside the published surface, which it never changes; records: `VERSION.toml`, read by `records.py`.

Reuse family logic through normal imports from family `src/`. Refactor within the authorized
change when needed; do not build chains of imports from older experiment folders. Leave existing
recorded versions intact. Cross-family mechanisms use the existing shared package or platform;
follow the root rules before introducing new platform tooling.

### Historical versions and selected baselines

Execute a recorded version or selected baseline only with
`qf-strategies rerun <family> <version> -- <command>`. It checks out the version's `src_commit`
in a temporary worktree, uses that commit's `uv.lock`, links the prepared inputs, runs the command
from the repository root, and removes the worktree. Use command paths as they existed at that
commit. Versions recorded before `src_commit` use `optimization/RERUN.toml`'s `default_commit`
and extra `links`.

- Never use `qf-strategies run --memory-version ...` for this: it runs the current checkout, and
  the version argument only labels outputs. New research may use current code after its reviewed
  implementation commit.
- `select_research_baseline` selects saved results by version, run and manifest. It executes
  nothing and pins no future execution.
- Viz **Update backtest** reruns every preset on the version's recorded commit when one exists,
  and on the current checkout only when none is recorded. From the command line, on commits that
  contain the update module: `python -m strategies.backtest_updates <absolute-db-root> <family>
  <version> --here` under `rerun`. Updates belong in `<version>/updated/`, never in the original
  run or published surface.

Code history does not freeze external data. If required inputs have moved, changed incompatibly
or disappeared, record the blocker; do not patch the old commit or claim exact reproduction.
Do not keep retired implementations beside current code to make old versions import at HEAD;
Git preserves them. Remove unused code as part of an authorized replacement; tag the last
commit before a large retirement.

## 7. Retiring

Retire a family only on operator request: delete its code with `git rm -r
extensions/lib/<family>` (Git keeps it; name the last commit that has it in the commit message)
and move `db/strategies/<family>/` to `db/strategies/_archive/<family>/`. Never add an archived status to the registry. Restoring checks the family out of
that commit and reverses the DB move. Afterwards `uv run qf-strategies validate` passes and
`qf-strategies list` reflects the change.
