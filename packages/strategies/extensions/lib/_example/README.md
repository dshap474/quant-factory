# example

A reference scaffold for a strategy family. Copy its directory shape when starting a family;
follow the current [shared strategy rules](../../../AGENTS.md) for the workflow and authority.

## Surfaces

| Surface          | Holds                                                            | Written by |
| ---------------- | ---------------------------------------------------------------- | ---------- |
| `src/` | Current strategy implementation using the shared runner and backtester | Family developers, with review |
| `optimization/` | Experiment-specific arms, comparisons and required version records | Researcher and reviewer |
| `references/`    | Source material the strategy replicates or designs against (books, papers, reference implementations) — read-only inputs | Maintainer |
| `verification/`  | Independent goldens per area of `src/`, plus `e2e/` tests of the production entry point ([layout](verification/README.md)); no unit tests | Reviewers independent of the code under test |

## Catalog discovery

A family enters the `qf-strategies` catalog only through code: a module literally named
`runner.py` inside `src/<package>/` that calls `StrategyRegistry.register(...)`. There is no
on-disk catalog file. Here that is `src/example_strategy/runner.py`: `ExampleRunner` emits
`StrategyWeights` for two presets — `control` (equal weight over SPY/QQQ/GLD/TLT) and
`candidate` (a capped 30-session momentum tilt; v002 scales it by inverse volatility) — from the
public `example` feature panel (Yahoo Finance via `packages/data/extensions/datasets/example`), on the
newest complete inputs.

## Version history layout

The current version lives directly at `optimization/vNNN/` (`v002/`, implemented, not yet run);
every recorded prior version lives under `optimization/version/vNNN/` (`v001/`, sealed
`not_tested`). The next version is the highest version folder + 1. Every version folder has the full
shared rules §5 shape, so either one is a correct example to copy:

| File | Holds |
| ---- | ----- |
| `SPEC.md` | Hypothesis, frozen parameters, control, decision criteria — before coding |
| `CHANGELOG.md` | The change, why, reused components, the control |
| `REVIEW.md` | Independent implementation review and readiness |
| `HYPOTHESIS_OUTCOME.md` | The verdict bound to a run (or why there is none) |
| `VERSION.toml` | `version`, `phase`, `status`, `backtest_run_at`, `backtest_run_at_source` |
| `rerun.py` | `PRESETS` and `build(preset)` → a `StrategyRunner` for that arm |
| `run.py` | Current version only: runs each arm through `rerun.build` and applies the SPEC criterion |

`rerun.py` is the one code path: `run.py` publishes the backtest through it. Execute a recorded
version on its recorded commit with the explicit `qf-strategies rerun` command (shared rules §6);
Update backtest also runs on the recorded commit when one exists. Add missing required
records explicitly, but leave recorded implementations and evidence intact. A record not written at the time is a stub
that says so and links the evidence. `verification/e2e/test_runner.py` shows an end-to-end check.

This example has no `tests/`; its checks live in `verification/`. `verification/` holds the checks the code is
judged by, and a change to the family's code should not also change those checks.

## Review and checks

Run the applicable existing checks. New checks require a user request and an independent
validator. Derive expected answers from source examples or another independent reference, use
small fixtures, and document numerical tolerances. Recorded-output checks detect changes but
do not alone establish correctness. Do not weaken checks to make a candidate pass or add a new
verification workflow for each experiment.

## Lifecycle pointers

Read [packages/strategies/AGENTS.md](../../../AGENTS.md) before work here. Research versions may
edit family `src/`; experiment-specific arms and records live in `optimization/vNNN/`. Commit
and review the implementation before its backtest, and record its `src_commit`. Editing current
code does not select a baseline. Run artifacts publish to `db/research/strategies/example/`,
not into this package. Use existing shared engines; changes to those engines need explicit
user approval and independent acceptance review.
