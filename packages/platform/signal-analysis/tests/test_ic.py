"""Independent correlation, coverage, and temporal-isolation tests of public IC.

Usage: uv run pytest packages/platform/signal-analysis/tests/test_ic.py
"""

import math
from decimal import Decimal, localcontext
from fractions import Fraction

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.ic import cross_sectional_ic

# --------------------------------------------------------------------------- #
# Known answers and aggregation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method", ["pearson", "spearman"])
@pytest.mark.parametrize("values,expected", [([1.0, 2.0, 3.0, 4.0], 1.0), ([4.0, 3.0, 2.0, 1.0], -1.0)])
def test_exact_ordering(panel, targets, method, values, expected):
    result = cross_sectional_ic(
        panel.with_columns(pl.Series("signal", values)), targets, target_ids=["next"], method=method, min_pairs=3
    )
    row = result.row(0, named=True)
    assert row["ic"] == pytest.approx(expected, abs=1e-12, rel=0)
    assert row["status"] == "ok"
    assert row["n_total"] == row["n_eligible"] == row["n_valid"] == 4


def test_average_rank_ties_have_hand_derived_answer(panel, targets):
    tied = panel.with_columns(pl.Series("signal", [1.0, 1.0, 2.0, 3.0]))
    result = cross_sectional_ic(tied, targets, target_ids=["next"], method="spearman", min_pairs=4)
    # Centered rank sums: xx=9/2, yy=5, xy=9/2 -> 3/sqrt(10).
    assert result["ic"][0] == pytest.approx(3 / math.sqrt(10), abs=1e-12, rel=0)


def test_dates_and_targets_are_separate_estimands(panel, targets):
    later_panel = panel.with_columns(
        pl.col("decision_time", "signal_available_at") + pl.duration(days=10),
    )
    later_targets = targets.with_columns(
        pl.col("decision_time", "target_start", "target_end") + pl.duration(days=10),
        pl.col("target").reverse(),
    )
    panels, outcomes = pl.concat([panel, later_panel]), pl.concat([targets, later_targets])
    alternate = outcomes.with_columns(pl.lit("inverse").alias("target_id"), -pl.col("target"))
    result = cross_sectional_ic(
        panels, pl.concat([outcomes, alternate]), target_ids=["next", "inverse"], method="pearson", min_pairs=3
    )
    # Pooling both dates would give zero; separate target/date cells give +/-1.
    assert result["ic"].to_list() == pytest.approx([-1, 1, 1, -1], abs=1e-12, rel=0)
    assert result["target_id"].to_list() == ["inverse", "next"] * 2
    original_first = result.filter(pl.col("decision_time") == panel["decision_time"][0])
    changed = later_targets.with_columns(pl.lit(0.5).alias("target"))
    modified = cross_sectional_ic(
        panels, pl.concat([targets, changed, alternate]), target_ids=["next", "inverse"], method="pearson", min_pairs=3
    )
    assert_frame_equal(modified.filter(pl.col("decision_time") == panel["decision_time"][0]), original_first)


# --------------------------------------------------------------------------- #
# Exclusions and undefined results
# --------------------------------------------------------------------------- #


def test_exclusion_precedence_and_conservation(panel, targets):
    # Expand to eight assets to activate every exclusion plus two valid pairs.
    more_panel = panel.with_columns(pl.col("asset") + "2")
    more_targets = targets.with_columns(pl.col("asset") + "2")
    inputs = pl.concat([panel, more_panel]).with_columns(
        pl.Series("eligible", [False, True, True, True, True, True, True, True]),
        pl.Series("signal", [None, None, float("inf"), 4.0, 5.0, 6.0, 7.0, 8.0]),
    )
    outcomes = (
        pl.concat([targets, more_targets])
        .with_columns(
            pl.Series(
                "target_status",
                [
                    "invalid_target",
                    "missing_target",
                    "invalid_price",
                    "ok",
                    "missing_exit_price",
                    "invalid_price",
                    "ok",
                    "ok",
                ],
            ),
            pl.Series("target", [None, None, None, 0.4, None, None, 0.7, 0.8]),
        )
        .filter(pl.col("asset") != "D")
    )
    row = cross_sectional_ic(inputs, outcomes, target_ids=["next"], method="spearman", min_pairs=2).row(0, named=True)
    assert [
        row[f"n_{name}"]
        for name in ("ineligible", "missing_signal", "nonfinite_signal", "missing_target", "invalid_target")
    ] == [1, 1, 1, 2, 1]
    assert row["n_total"] == 8
    assert row["n_eligible"] == 7
    assert row["n_valid"] == 2
    assert row["ic"] == pytest.approx(1, abs=1e-12, rel=0)
    assert (
        row["n_valid"]
        + sum(
            value
            for key, value in row.items()
            if key in {"n_ineligible", "n_missing_signal", "n_nonfinite_signal", "n_missing_target", "n_invalid_target"}
        )
        == row["n_total"]
    )


@pytest.mark.parametrize(
    "signal_constant,target_constant,status",
    [
        (True, False, "constant_signal"),
        (False, True, "constant_target"),
        (True, True, "constant_both"),
    ],
)
def test_constant_statuses_and_minimum_precedence(panel, targets, signal_constant, target_constant, status):
    if signal_constant:
        panel = panel.with_columns(pl.lit(1.0).alias("signal"))
    if target_constant:
        targets = targets.with_columns(pl.lit(0.0).alias("target"))
    result = cross_sectional_ic(panel, targets, target_ids=["next"], method="pearson", min_pairs=4)
    assert result["status"].to_list() == [status]
    assert result["ic"].to_list() == [None]
    short = cross_sectional_ic(panel, targets, target_ids=["next"], method="spearman", min_pairs=5)
    assert short["status"].to_list() == ["insufficient_pairs"]


def test_all_excluded_dates_and_missing_targets_are_retained(panel, targets):
    result = cross_sectional_ic(panel, targets, target_ids=["not_available"], method="pearson", min_pairs=2)
    assert result["n_missing_target"].to_list() == [4]
    assert result["status"].to_list() == ["insufficient_pairs"]
    excluded = cross_sectional_ic(
        panel.with_columns(pl.lit(False).alias("eligible")), targets, target_ids=["next"], method="pearson", min_pairs=2
    )
    assert excluded.height == 1
    assert excluded["n_ineligible"].to_list() == [4]
    assert excluded["n_valid"].to_list() == [0]
    empty = cross_sectional_ic(panel.head(0), targets.head(0), target_ids=["next"], method="pearson", min_pairs=2)
    assert empty.schema == result.schema
    assert empty.is_empty()
    assert result.schema["min_pairs"] == result.schema["n_missing_target"] == pl.UInt64
    assert result.schema["ic"] == pl.Float64
    assert result.schema["decision_time"] == pl.Datetime("us", "UTC")


def test_orphans_fail_but_unrequested_valid_rows_are_ignored(panel, targets):
    orphan = targets.head(1).with_columns(pl.lit("unknown_asset").alias("asset"))
    with pytest.raises(ValueError, match="absent"):
        cross_sectional_ic(panel, orphan, target_ids=["next"], method="pearson", min_pairs=2)
    with pytest.raises(ValueError, match="absent"):
        cross_sectional_ic(panel.head(0), targets, target_ids=["next"], method="pearson", min_pairs=2)
    other = orphan.with_columns(pl.lit("other").alias("target_id"))
    expected = cross_sectional_ic(panel, targets, target_ids=["next"], method="pearson", min_pairs=2)
    actual = cross_sectional_ic(panel, pl.concat([targets, other]), target_ids=["next"], method="pearson", min_pairs=2)
    assert_frame_equal(actual, expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_ids": []},
        {"target_ids": "next"},
        {"target_ids": ["next", "next"]},
        {"target_ids": [""]},
        {"target_ids": [1]},
        {"method": "cosine"},
        {"min_pairs": True},
        {"min_pairs": 1},
        {"min_pairs": 2.5},
        {"min_pairs": 2**64},
    ],
)
def test_bad_parameters_rejected(panel, targets, kwargs):
    parameters = {"target_ids": ["next"], "method": "pearson", "min_pairs": 2, **kwargs}
    with pytest.raises(ValueError):
        cross_sectional_ic(panel, targets, **parameters)


def test_public_metric_validates_inputs_and_ignores_extra_column_names(panel, targets):
    with pytest.raises(ValueError, match="duplicate"):
        cross_sectional_ic(
            pl.concat([panel, panel.head(1)]), targets, target_ids=["next"], method="pearson", min_pairs=2
        )
    with pytest.raises(ValueError, match="signal_available_at"):
        cross_sectional_ic(
            panel.with_columns(pl.col("signal_available_at") + pl.duration(days=1)),
            targets,
            target_ids=["next"],
            method="pearson",
            min_pairs=2,
        )
    expected = cross_sectional_ic(panel, targets, target_ids=["next"], method="pearson", min_pairs=2)
    actual = cross_sectional_ic(
        panel.with_columns(pl.lit("collision").alias("target_status")),
        targets.with_columns(pl.lit(99.0).alias("signal")),
        target_ids=["next"],
        method="pearson",
        min_pairs=2,
    )
    assert_frame_equal(actual, expected)


# --------------------------------------------------------------------------- #
# Independent precision and invariance oracles
# --------------------------------------------------------------------------- #


def _decimal_pearson(left, right, precision):
    # Exact rational centering avoids oracle cancellation, even for subnormals.
    x, y = [Fraction(v) for v in left], [Fraction(v) for v in right]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    product = sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)
    with localcontext() as ctx:
        ctx.prec = precision
        covariance = Decimal(numerator.numerator) / Decimal(numerator.denominator)
        variance_product = Decimal(product.numerator) / Decimal(product.denominator)
        return float(covariance / variance_product.sqrt())


@pytest.mark.parametrize(
    "left,right",
    [
        ([-3.0, 1.0, 2.0, 8.0], [4.0, -2.0, 7.0, 1.0]),
        ([-1.7e308, 1.7e308, 0.0, 1e307], [4.0, -2.0, 7.0, 1.0]),
        ([1e100 + i * math.ulp(1e100) for i in range(4)], [4.0, -2.0, 7.0, 1.0]),
        ([math.ulp(0.0) * i for i in range(1, 5)], [4.0, -2.0, 7.0, 1.0]),
    ],
)
def test_pearson_against_precision_doubled_independent_formula(panel, targets, left, right):
    expected = _decimal_pearson(left, right, 80)
    assert expected == _decimal_pearson(left, right, 160)
    result = cross_sectional_ic(
        panel.with_columns(pl.Series("signal", left)),
        targets.with_columns(pl.Series("target", right)),
        target_ids=["next"],
        method="pearson",
        min_pairs=4,
    )
    assert result["status"].to_list() == ["ok"]
    assert result["ic"][0] == pytest.approx(expected, abs=1e-12, rel=0)
    assert -1 <= result["ic"][0] <= 1


@pytest.mark.parametrize("method", ["pearson", "spearman"])
def test_permutation_affine_and_asset_renaming_invariance(panel, targets, method):
    panel = panel.with_columns(pl.Series("signal", [3.0, -2.0, 0.0, 7.0]))
    before_panel, before_targets = panel.clone(), targets.clone()
    result = cross_sectional_ic(panel, targets, target_ids=["next"], method=method, min_pairs=3)
    permuted = cross_sectional_ic(panel.reverse(), targets.reverse(), target_ids=["next"], method=method, min_pairs=3)
    assert_frame_equal(result, permuted)
    transformed = panel.with_columns((pl.col("signal") * 8 + 16), pl.col("asset") + "_renamed")
    transformed_targets = targets.with_columns(pl.col("asset") + "_renamed")
    actual = cross_sectional_ic(transformed, transformed_targets, target_ids=["next"], method=method, min_pairs=3)
    assert actual["ic"].to_list() == pytest.approx(result["ic"].to_list(), abs=1e-12, rel=0)
    if method == "spearman":
        nonlinear = cross_sectional_ic(
            panel.with_columns(pl.col("signal").pow(3)), targets, target_ids=["next"], method=method, min_pairs=3
        )
        assert nonlinear["ic"].to_list() == result["ic"].to_list()
    assert_frame_equal(panel, before_panel)
    assert_frame_equal(targets, before_targets)
