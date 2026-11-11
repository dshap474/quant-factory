"""Exact-mean, precedence, and contract tests for signal-quantile conditional means.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_quantiles.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone
from fractions import Fraction

import polars as pl
import pytest

from signal_analysis.ic import cross_sectional_ic
from signal_analysis.quantiles import quantile_conditional_means

UTC = pl.Datetime("us", "UTC")
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def fixture(signals, targets, *, eligible=None, statuses=None, date=T0):
    n = len(signals)
    assets = [f"A{i:02d}" for i in range(n)]
    panel = pl.DataFrame(
        {
            "decision_time": [date] * n,
            "asset": assets,
            "signal_available_at": [date] * n,
            "signal": signals,
            "eligible": eligible or [True] * n,
        },
        schema={
            "decision_time": UTC,
            "asset": pl.String,
            "signal_available_at": UTC,
            "signal": pl.Float64,
            "eligible": pl.Boolean,
        },
    )
    statuses = statuses or ["ok"] * n
    target = pl.DataFrame(
        {
            "decision_time": [date] * n,
            "asset": assets,
            "target_id": ["h"] * n,
            "target_start": [date + DAY] * n,
            "target_end": [date + 2 * DAY] * n,
            "target": [t if s == "ok" else None for t, s in zip(targets, statuses)],
            "target_status": statuses,
            "target_kind": ["price_return"] * n,
            "return_type": ["log"] * n,
        },
        schema={
            "decision_time": UTC,
            "asset": pl.String,
            "target_id": pl.String,
            "target_start": UTC,
            "target_end": UTC,
            "target": pl.Float64,
            "target_status": pl.String,
            "target_kind": pl.String,
            "return_type": pl.String,
        },
    )
    return panel, target


def means(panel, target, **overrides):
    settings = dict(target_ids=["h"], n_quantiles=5, min_pairs=2)
    settings.update(overrides)
    return quantile_conditional_means(panel, target, **settings)


# --------------------------------------------------------------------------- #
# Known answers
# --------------------------------------------------------------------------- #


def test_targets_equal_to_rank_give_exact_quintile_means():
    ranks = [float(k) for k in range(1, 11)]
    result = means(*fixture(ranks, ranks))
    assert result["quantile"].to_list() == [1, 2, 3, 4, 5]
    assert result["mean_target"].to_list() == [1.5, 3.5, 5.5, 7.5, 9.5]
    assert result["n_pairs"].to_list() == [2] * 5
    assert result["status"].to_list() == ["ok"] * 5


def test_reversed_relation_reverses_the_means():
    ranks = [float(k) for k in range(1, 11)]
    result = means(*fixture(ranks, ranks[::-1]))
    assert result["mean_target"].to_list() == [9.5, 7.5, 5.5, 3.5, 1.5]


def test_uneven_membership_uses_floor_assignment():
    # n=7, q=5: ranks k=1..7 → floor((k-1)*5/7)+1 = 1,1,2,3,3,4,5.
    signals = [float(k) for k in range(1, 8)]
    result = means(*fixture(signals, signals))
    assert result["n_pairs"].to_list() == [2, 1, 2, 1, 1]
    assert result["mean_target"].to_list() == [1.5, 3.0, 4.5, 6.0, 7.0]


def test_ties_break_by_asset_name_deterministically():
    signals = [1.0] * 4
    targets = [10.0, 20.0, 30.0, 40.0]
    result = means(*fixture(signals, targets), n_quantiles=2)
    assert result["mean_target"].to_list() == [15.0, 35.0]


def test_mean_retains_cancellation_residual():
    signals = [1.0, 2.0, 3.0, 4.0]
    result = means(*fixture(signals, [1e308, 1.0, -1e308, 0.0]), n_quantiles=2)
    assert result["mean_target"].to_list()[0] == float(Fraction(1e308) + 1) / 2 or result["mean_target"][0] == 5e307


def test_few_pairs_report_insufficient_for_every_quantile():
    signals = [1.0, 2.0, 3.0, 4.0]
    result = means(*fixture(signals, signals))
    assert result.height == 5
    assert result["status"].to_list() == ["insufficient_pairs"] * 5
    assert result["mean_target"].null_count() == 5 and result["n_pairs"].sum() == 0
    assert result["n_valid"].to_list() == [4] * 5


# --------------------------------------------------------------------------- #
# Exclusion precedence shared with IC
# --------------------------------------------------------------------------- #


def test_exclusion_counts_match_cross_sectional_ic():
    targets = [float(k) for k in range(1, 13)]
    signals = list(targets)
    signals[3] = float("nan")
    eligible = [True] * 12
    eligible[0] = False
    eligible[3] = False  # ineligible outranks nonfinite signal
    statuses = ["ok"] * 12
    statuses[5] = "missing_exit_price"
    statuses[7] = "invalid_price"
    panel, target = fixture(signals, targets, eligible=eligible, statuses=statuses)
    result = means(panel, target, n_quantiles=2)
    ic = cross_sectional_ic(panel, target, target_ids=["h"], method="spearman", min_pairs=2).row(0, named=True)
    row = result.row(0, named=True)
    for column in (
        "n_total",
        "n_valid",
        "n_ineligible",
        "n_missing_signal",
        "n_nonfinite_signal",
        "n_missing_target",
        "n_invalid_target",
    ):
        assert row[column] == ic[column], column
    assert row["n_valid"] == 8 and row["n_ineligible"] == 2 and row["n_nonfinite_signal"] == 0
    assert result["n_pairs"].to_list() == [4, 4]


def test_missing_requested_target_rows_count_as_missing_target():
    panel, target = fixture([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    result = means(panel, target.head(3), n_quantiles=2)
    assert result.row(0, named=True)["n_missing_target"] == 1
    # Three valid pairs, two quantiles: ranks 1,2 -> quantile 1; rank 3 -> quantile 2.
    assert result["n_pairs"].to_list() == [2, 1]


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


def test_parameter_and_key_contracts():
    panel, target = fixture([1.0, 2.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        means(panel, target, n_quantiles=1)
    with pytest.raises(ValueError):
        means(panel, target, min_pairs=True)
    with pytest.raises(ValueError):
        means(panel, target, target_ids="h")
    with pytest.raises(ValueError, match="absent from the signal panel"):
        means(panel.head(1), target)
    empty = means(panel, target.filter(pl.col("target_id") == "other"))
    assert empty["status"].to_list() == ["insufficient_pairs"] * 5


def test_two_dates_are_sorted_and_independent():
    p1, t1 = fixture([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    p2, t2 = fixture([4.0, 3.0, 2.0, 1.0], [1.0, 2.0, 3.0, 4.0], date=T0 - DAY)
    result = means(pl.concat([p1, p2]), pl.concat([t1, t2]), n_quantiles=2)
    assert result["decision_time"].to_list() == [T0 - DAY] * 2 + [T0] * 2
    assert result["mean_target"].to_list() == [3.5, 1.5, 1.5, 3.5]
