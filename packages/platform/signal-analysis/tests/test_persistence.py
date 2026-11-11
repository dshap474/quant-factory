"""Known-answer and coverage tests for signal rank autocorrelation across decision dates.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_persistence.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from signal_analysis.persistence import signal_rank_autocorrelation

UTC = pl.Datetime("us", "UTC")
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def panel(rows):
    """rows: (day_index, asset, signal, eligible)."""
    return pl.DataFrame(
        {
            "decision_time": [T0 + d * DAY for d, *_ in rows],
            "asset": [a for _, a, *_ in rows],
            "signal_available_at": [T0 + d * DAY for d, *_ in rows],
            "signal": [s for _, _, s, *_ in rows],
            "eligible": [r[3] if len(r) > 3 else True for r in rows],
        },
        schema={
            "decision_time": UTC,
            "asset": pl.String,
            "signal_available_at": UTC,
            "signal": pl.Float64,
            "eligible": pl.Boolean,
        },
    )


ASSETS = ["A", "B", "C", "D"]


def constant_panel(days=4):
    return panel([(d, a, float(i)) for d in range(days) for i, a in enumerate(ASSETS)])


def alternating_panel(days=4):
    return panel([(d, a, float(i if d % 2 == 0 else 3 - i)) for d in range(days) for i, a in enumerate(ASSETS)])


# --------------------------------------------------------------------------- #
# Known answers
# --------------------------------------------------------------------------- #


def test_constant_ranking_gives_one_at_every_lag():
    result = signal_rank_autocorrelation(constant_panel(), lags=[1, 2, 3], min_pairs=2)
    assert result["lag"].to_list() == [1, 2, 3]
    assert result["mean_rank_corr"].to_list() == pytest.approx([1.0, 1.0, 1.0], abs=1e-12)
    assert result["n_dates_lagged"].to_list() == [3, 2, 1]
    assert result["n_dates"].to_list() == [3, 2, 1]
    assert result["n_dates_supplied"].to_list() == [4, 4, 4]
    assert result["status"].to_list() == ["ok"] * 3


def test_per_date_reversal_gives_minus_one_at_lag_one_and_plus_one_at_lag_two():
    result = signal_rank_autocorrelation(alternating_panel(), lags=[1, 2], min_pairs=2)
    assert result["mean_rank_corr"].to_list() == pytest.approx([-1.0, 1.0], abs=1e-12)


def test_lag_beyond_history_has_no_dates():
    result = signal_rank_autocorrelation(constant_panel(), lags=[4], min_pairs=2)
    row = result.row(0, named=True)
    assert row["n_dates_lagged"] == 0 and row["status"] == "no_valid_dates" and row["mean_rank_corr"] is None


def test_asset_entering_mid_way_is_excluded_from_the_lagged_pair():
    rows = [(d, a, float(i)) for d in range(3) for i, a in enumerate(ASSETS)]
    rows.append((2, "E", 10.0))  # E only exists on day 2
    result = signal_rank_autocorrelation(panel(rows), lags=[1], min_pairs=2, per_date=True)
    assert result["n_pairs"].to_list() == [4, 4]
    assert result["lagged_decision_time"].to_list() == [T0, T0 + DAY]


def test_ineligible_and_nonfinite_signals_are_excluded_on_either_date():
    rows = [(d, a, float(i)) for d in range(2) for i, a in enumerate(ASSETS)]
    rows[0] = (0, "A", 0.0, False)
    rows[5] = (1, "B", float("nan"))
    result = signal_rank_autocorrelation(panel(rows), lags=[1], min_pairs=2, per_date=True)
    assert result["n_pairs"].to_list() == [2]


def test_min_pairs_and_constant_sides_report_status_per_date():
    rows = [(d, a, float(i)) for d in range(2) for i, a in enumerate(ASSETS)]
    few = signal_rank_autocorrelation(panel(rows), lags=[1], min_pairs=5, per_date=True)
    assert few["status"].to_list() == ["insufficient_pairs"]
    flat = panel([(0, a, 1.0) for a in ASSETS] + [(1, a, float(i)) for i, a in enumerate(ASSETS)])
    result = signal_rank_autocorrelation(flat, lags=[1], min_pairs=2, per_date=True)
    assert result["status"].to_list() == ["constant_target"]
    assert signal_rank_autocorrelation(flat, lags=[1], min_pairs=2)["status"].to_list() == ["no_valid_dates"]


def test_lags_count_decision_dates_not_elapsed_time():
    rows = [(d, a, float(i)) for d in (0, 1, 5) for i, a in enumerate(ASSETS)]
    result = signal_rank_autocorrelation(panel(rows), lags=[1], min_pairs=2, per_date=True)
    assert result["lagged_decision_time"].to_list() == [T0, T0 + DAY]
    assert result["decision_time"].to_list() == [T0 + DAY, T0 + 5 * DAY]


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lags", [[], [0], [1, 1], [True], "1"])
def test_bad_lags_raise(lags):
    with pytest.raises(ValueError):
        signal_rank_autocorrelation(constant_panel(), lags=lags, min_pairs=2)


def test_bad_min_pairs_and_panel_raise():
    with pytest.raises(ValueError):
        signal_rank_autocorrelation(constant_panel(), lags=[1], min_pairs=1)
    with pytest.raises(TypeError):
        signal_rank_autocorrelation(constant_panel().drop("eligible"), lags=[1], min_pairs=2)
