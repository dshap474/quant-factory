# v001 — SPEC (illustrative)

This is a scaffold example, not a real preregistration. A real SPEC is frozen before any
implementation: the hypothesis, the frozen parameters, the named control, and the pass/fail
criteria are all pinned in the preregistration commit (the same commit that creates the version folder), and the file is never edited afterward.

## Hypothesis

Adding a toy momentum tilt to the equal-weight book improves annualized Sharpe
against the control by more than the preregistered threshold.

## Frozen parameters

- Lookback: 30 rows (trading sessions on the ETFs' common dates, about six calendar weeks)
- Tilt cap: ±10% of equal weight
- Control: equal-weight book (same data window, same costs)

## Decision criteria

- SUPPORTED if candidate-minus-control Sharpe delta ≥ +0.10 on the full causal backtest.
- FALSIFIED otherwise. Correctness failures stop the run; disappointing economics do not.

## Artifacts

Run outputs land under `db/research/strategies/example/v001/...`; this tree seals with the
recorded outcome and is immutable afterward.
