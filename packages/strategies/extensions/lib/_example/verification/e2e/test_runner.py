"""The example runner: every version's rerun builds its presets, and the book weights are sane.

USAGE: uv run pytest packages/strategies/extensions/lib/_example/verification -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest
from example_strategy.runner import ASSETS, ExampleRunner, book_weights
from strategies.backtest_updates import load_rerun, targets

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("family", "version", "preset"), targets("_example"))
def test_rerun_builds_each_preset(family, version, preset):
    runner = load_rerun(family, version).build(preset)
    assert isinstance(runner, ExampleRunner)
    assert (runner.run_config.memory_version, runner.run_config.strategy_id, runner.run_config.save) == (version, preset, False)


@pytest.mark.parametrize("vol_scaled", [False, True])
def test_candidate_tilts_toward_momentum_and_stays_invested(vol_scaled):
    days = 60
    growth = {"us:SPY": 0.002, "us:QQQ": 0.001, "us:GLD": 0.0, "us:TLT": -0.001}  # SPY strongest
    noise = np.random.default_rng(0).normal(0.0, 0.001, (days, len(ASSETS)))
    prices = pl.DataFrame({
        "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(days)],
        **{a: np.cumprod(1.0 + growth[a] + noise[:, j]) for j, a in enumerate(ASSETS)},
    })
    control = book_weights(prices, "control", vol_scaled)
    candidate = book_weights(prices, "candidate", vol_scaled)
    assert control.select(ASSETS).to_numpy().tolist() == [[0.25] * 4] * days
    assert np.allclose(candidate.select(ASSETS).sum_horizontal().to_numpy(), 1.0)
    assert (candidate["CASH"] == 0.0).all()
    assert (candidate["us:SPY"] > candidate["us:TLT"]).all()
    assert candidate.select(ASSETS).to_numpy().max() <= 1.1 / 3.8 + 1e-12  # one asset at +10%, three at -10%
