# CHANGELOG — v002

## Change

The v001 momentum tilt is scaled per asset by inverse 20-session realized volatility (relative to
the cross-sectional mean) before the ±10% cap. Lookback (30 sessions), cap, assets, costs and the
equal-weight control are unchanged from v001.

## Why

The SPEC's hypothesis (illustrative, untested): turnover costs the unscaled tilt Sharpe, and
scaling by inverse volatility recovers it.

## Reused components

- Family runner `example_strategy.runner.ExampleRunner`; v002 differs from v001 only in
  `VOL_SCALED["v002"] = True`.
- [rerun.py](rerun.py) builds both arms; [run.py](run.py) runs them through `rerun.build` and
  applies the SPEC criterion.

## Control

`control`: the equal-weight book on the same window and the same 5 bps ledger costs.
