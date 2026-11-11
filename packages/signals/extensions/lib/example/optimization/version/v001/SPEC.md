# v001 — SPEC (illustrative)

This is a scaffold example, not a real preregistration. A real SPEC is frozen before any
implementation: the hypothesis, the frozen parameters, the point-in-time policy, the named control, and
the pass/fail criteria are all pinned in the preregistration commit (the same commit that creates the version folder), and the file is never edited afterward.

## Hypothesis

The sign of 30-day BTC momentum at the close of day `t` carries positive out-of-sample information
about next-day BTC return against a zero-information control.

## Frozen parameters

- Input: `crypto:BTC` `close` from the `example` feature panel; no shift, row `t` uses the close
  labeled `t` (AGENTS.md §2)
- Prediction: `sign(close[t] / close[t-30] - 1)` in {-1, 0, +1}
- Control: the zero-information baseline, mean IC = 0
- Evaluation: causal expanding-window walk-forward; Spearman IC of `prediction` against
  next-day BTC return

## Decision criteria

- SUPPORTED if mean OOS IC ≥ +0.02 with a positive one-sided 95% bootstrap lower bound.
- FALSIFIED otherwise. Correctness failures stop the run; disappointing statistics do not.

## Artifacts

Run outputs land under `db/research/signals/example/v001/...`; this tree seals with the
recorded outcome and is immutable afterward. Nothing is appended to `db/signals/` — that is the
registered runner's production history, not a research version's.
