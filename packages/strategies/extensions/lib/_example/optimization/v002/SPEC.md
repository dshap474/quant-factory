# v002 — SPEC (illustrative)

Scaffold example of the *current* version: the latest `vNNN` lives directly at
`optimization/vNNN/`; when it seals and a new version is preregistered, this whole directory
moves unchanged to `optimization/version/vNNN/`.

## Hypothesis

Scaling the v001 momentum tilt by inverse volatility raises annualized Sharpe over the
equal-weight control by at least +0.10.

## Frozen parameters

- Input: `close` for `us:SPY`, `us:QQQ`, `us:GLD`, `us:TLT` from the `example` feature panel
  (Yahoo Finance daily, dividend-adjusted; row `T` = the US session close of `T`; the adjustment
  rewrites past levels, which this example accepts as a stated caveat — see the data example README)
- Lookback: 30 rows, i.e. trading sessions (unchanged from v001 — deltas from the prior version are stated explicitly)
- Tilt scaled by inverse 20-session realized volatility relative to the cross-sectional mean, cap ±10%
- Control: equal-weight book

## Decision criteria

- SUPPORTED if candidate-minus-control Sharpe delta ≥ +0.10 on the full causal backtest.
- FALSIFIED otherwise.

`HYPOTHESIS_OUTCOME.md` records "none yet" until a valid run replaces it with the verdict;
`phase = "implemented"` means the code exists and has not been run.
