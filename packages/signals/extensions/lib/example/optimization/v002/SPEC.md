# v002 — SPEC (illustrative)

Scaffold example of the *current* version: the latest `vNNN` lives directly at
`optimization/vNNN/`; when it seals and a new version is preregistered, this whole directory
moves unchanged to `optimization/version/vNNN/`.

## Hypothesis

Scaling the v001 momentum sign by inverse 20-day realized volatility raises the out-of-sample
information coefficient over the raw sign.

## Frozen parameters

- Input: `crypto:BTC` `close` from the `example` feature panel (Yahoo Finance daily, adjusted;
  row `T` = the completed UTC day `T`)
- Lookback: 30 daily bars (unchanged from v001 — deltas from the prior version are stated explicitly)
- Prediction: momentum sign × inverse 20-day realized volatility relative to its expanding mean, winsorized at ±3
- Point-in-time: no shift; row `T` uses the close labeled `T` (AGENTS.md §2); evaluation scores the
  prediction labeled `T` against the return from `T` to `T+1`
- Control: v001 raw momentum sign, same data window, built with
  `ExampleRunner.from_preset("default", memory_version="v001")`
- Evaluation: causal expanding-window walk-forward; Spearman IC of `prediction` against
  next-day BTC return

## Decision criteria

- SUPPORTED if candidate-minus-control mean OOS IC delta ≥ +0.01 across all folds.
- FALSIFIED otherwise.

`HYPOTHESIS_OUTCOME.md` holds only a "none yet" placeholder — the real record is written only
after a valid run, and `phase = "implemented"` says the code exists but has not run.
