"""Hand-derived, invariance, precedence, and contract tests for directional scores.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_direction.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone
from fractions import Fraction

import polars as pl
import pytest

from signal_analysis.direction import directional_scores
from signal_analysis.ic import cross_sectional_ic

UTC = pl.Datetime("us", "UTC")
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
COUNTS = ("n_positive_signal", "n_negative_signal", "n_zero_signal", "n_hits", "n_misses", "n_ties")


def fixture(signals, targets, *, eligible=None, statuses=None, date=T0, target_id="next"):
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
    frame = pl.DataFrame(
        {
            "decision_time": [date] * n,
            "asset": assets,
            "target_id": [target_id] * n,
            "target_start": [date + DAY] * n,
            "target_end": [date + 2 * DAY] * n,
            "target": [t if s == "ok" else None for t, s in zip(targets, statuses, strict=True)],
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
    return panel, frame


def score(signals, targets, *, min_pairs=2, **kwargs):
    panel, frame = fixture(signals, targets, **kwargs)
    return directional_scores(panel, frame, target_ids=["next"], min_pairs=min_pairs).row(0, named=True)


# --------------------------------------------------------------------------- #
# Known answers
# --------------------------------------------------------------------------- #


def test_hand_derived_signed_mean_reference_and_hit_rate():
    # signs + - + -, targets .1 .2 .3 .4: signed values .1 -.2 .3 -.4 sum -.2 -> mean -.05;
    # always-long mean .25; agreements hit, miss, hit, miss -> hit rate 1/2.
    row = score([1.0, -2.0, 3.0, -4.0], [0.1, 0.2, 0.3, 0.4])
    exact = Fraction(1, 10) - Fraction(2, 10) + Fraction(3, 10) - Fraction(4, 10)
    assert row["signed_mean"] == pytest.approx(float(exact / 4), abs=1e-15, rel=0)
    assert row["mean_target"] == pytest.approx(0.25, abs=1e-15, rel=0)
    assert row["hit_rate"] == 0.5
    assert row["status"] == "ok"
    assert [row[c] for c in COUNTS] == [2, 2, 0, 2, 2, 0]
    assert row["n_total"] == row["n_eligible"] == row["n_valid"] == 4


def test_zero_signal_is_flat_and_zero_target_is_a_tie():
    # signal 0 contributes 0 to the signed mean and stays in the denominator; a zero
    # target with a nonzero signal is a tie, so the hit rate is over the two decided pairs.
    row = score([0.0, 2.0, -1.0, 3.0], [0.5, 0.0, -0.2, -0.4])
    assert row["signed_mean"] == pytest.approx((0.0 + 0.0 + 0.2 - 0.4) / 4, abs=1e-15, rel=0)
    assert row["mean_target"] == pytest.approx((0.5 + 0.0 - 0.2 - 0.4) / 4, abs=1e-15, rel=0)
    assert [row[c] for c in COUNTS] == [2, 1, 1, 1, 1, 2]
    assert row["hit_rate"] == 0.5


def test_all_ties_gives_null_hit_rate_but_finite_means():
    row = score([0.0, 0.0, 0.0], [0.1, -0.1, 0.3])
    assert row["signed_mean"] == 0.0
    assert row["mean_target"] == pytest.approx(0.1, abs=1e-15, rel=0)
    assert row["hit_rate"] is None
    assert row["status"] == "ok"
    assert row["n_ties"] == 3


def test_long_flat_rule_is_the_average_of_signed_and_reference():
    # Following the sign long/short earns signed_mean; always long earns mean_target; long when
    # positive and flat otherwise earns their average, so one paired difference covers both.
    signals, targets = [2.0, -1.0, 0.5, -3.0, 1.0], [0.3, 0.1, -0.2, -0.5, 0.4]
    row = score(signals, targets)
    long_flat = sum(t for s, t in zip(signals, targets, strict=True) if s > 0) / len(signals)
    assert (row["signed_mean"] + row["mean_target"]) / 2 == pytest.approx(long_flat, abs=1e-15, rel=0)


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


def test_negating_the_signal_negates_the_signed_mean_and_flips_hits():
    signals, targets = [1.5, -0.2, 3.0, -4.0, 0.7], [0.1, 0.2, -0.3, 0.4, -0.05]
    base, flipped = score(signals, targets), score([-s for s in signals], targets)
    assert flipped["signed_mean"] == pytest.approx(-base["signed_mean"], abs=1e-15, rel=0)
    assert flipped["mean_target"] == base["mean_target"]
    assert flipped["hit_rate"] == pytest.approx(1 - base["hit_rate"], abs=1e-15, rel=0)
    assert (flipped["n_hits"], flipped["n_misses"]) == (base["n_misses"], base["n_hits"])


def test_positive_scaling_of_the_signal_changes_nothing():
    signals, targets = [1.5, -0.2, 3.0, -4.0, 0.7], [0.1, 0.2, -0.3, 0.4, -0.05]
    base, scaled = score(signals, targets), score([1e6 * s for s in signals], targets)
    assert scaled == base


def test_negating_the_target_negates_both_means():
    signals, targets = [1.5, -0.2, 3.0, -4.0, 0.7], [0.1, 0.2, -0.3, 0.4, -0.05]
    base, flipped = score(signals, targets), score(signals, [-t for t in targets])
    assert flipped["signed_mean"] == pytest.approx(-base["signed_mean"], abs=1e-15, rel=0)
    assert flipped["mean_target"] == pytest.approx(-base["mean_target"], abs=1e-15, rel=0)
    assert flipped["hit_rate"] == pytest.approx(1 - base["hit_rate"], abs=1e-15, rel=0)


def test_dates_are_separate_estimands_and_rows_are_sorted():
    panel_a, targets_a = fixture([1.0, -1.0, 1.0], [0.1, 0.1, 0.1])
    panel_b, targets_b = fixture([1.0, 1.0, 1.0], [-0.1, -0.1, -0.1], date=T0 + DAY)
    result = directional_scores(
        pl.concat([panel_b, panel_a]), pl.concat([targets_b, targets_a]), target_ids=["next"], min_pairs=2
    )
    assert result["decision_time"].to_list() == [T0, T0 + DAY]
    assert result["signed_mean"].to_list() == pytest.approx([(0.1 - 0.1 + 0.1) / 3, -0.1], abs=1e-15, rel=0)
    assert result["hit_rate"].to_list() == pytest.approx([2 / 3, 0.0], abs=1e-15, rel=0)


def test_row_permutation_is_immaterial():
    panel, targets = fixture([1.5, -0.2, 3.0, -4.0, 0.7], [0.1, 0.2, -0.3, 0.4, -0.05])
    base = directional_scores(panel, targets, target_ids=["next"], min_pairs=2)
    shuffled = directional_scores(
        panel.reverse(), targets.sample(fraction=1.0, shuffle=True, seed=3), target_ids=["next"], min_pairs=2
    )
    assert shuffled.equals(base)


# --------------------------------------------------------------------------- #
# Coverage, precedence, and contracts
# --------------------------------------------------------------------------- #


def test_exclusion_counts_match_cross_sectional_ic_on_the_same_fixture():
    signals = [1.0, None, float("nan"), 2.0, -1.0, 0.5, 3.0]
    targets = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    eligible = [False, True, True, True, True, True, True]
    statuses = ["ok", "ok", "ok", "missing_exit_price", "invalid_target", "ok", "ok"]
    panel, frame = fixture(signals, targets, eligible=eligible, statuses=statuses)
    ours = directional_scores(panel, frame, target_ids=["next"], min_pairs=2).row(0, named=True)
    theirs = cross_sectional_ic(panel, frame, target_ids=["next"], method="pearson", min_pairs=2).row(0, named=True)
    for column in (
        "n_total",
        "n_eligible",
        "n_valid",
        "n_ineligible",
        "n_missing_signal",
        "n_nonfinite_signal",
        "n_missing_target",
        "n_invalid_target",
    ):
        assert ours[column] == theirs[column], column
    assert ours["n_valid"] == 2
    assert ours["signed_mean"] == pytest.approx((0.6 + 0.7) / 2, abs=1e-15, rel=0)
    assert ours["n_total"] == ours["n_valid"] + sum(
        ours[f"n_{r}"] for r in ("ineligible", "missing_signal", "nonfinite_signal", "missing_target", "invalid_target")
    )


def test_insufficient_pairs_reports_counts_with_null_scores():
    row = score([1.0, -1.0, 2.0], [0.1, 0.2, -0.3], min_pairs=4)
    assert row["status"] == "insufficient_pairs"
    assert row["signed_mean"] is None and row["mean_target"] is None and row["hit_rate"] is None
    assert [row[c] for c in COUNTS] == [2, 1, 0, 1, 2, 0]
    assert row["n_valid"] == 3


def test_missing_requested_target_is_a_coverage_loss_and_orphans_fail():
    panel, frame = fixture([1.0, -1.0, 2.0], [0.1, 0.2, -0.3])
    result = directional_scores(panel, frame, target_ids=["absent"], min_pairs=2)
    assert result.height == 1 and result["status"][0] == "insufficient_pairs" and result["n_missing_target"][0] == 3
    orphan = frame.head(1).with_columns(pl.lit("Z99").alias("asset"))
    with pytest.raises(ValueError, match="absent from the signal panel"):
        directional_scores(panel, pl.concat([frame, orphan]), target_ids=["next"], min_pairs=2)


def test_empty_typed_panel_returns_typed_empty_result():
    panel, frame = fixture([1.0], [0.1])
    result = directional_scores(panel.clear(), frame.clear(), target_ids=["next"], min_pairs=2)
    assert result.height == 0
    assert result.schema["signed_mean"] == pl.Float64 and result.schema["n_hits"] == pl.UInt64


@pytest.mark.parametrize("bad", [0, -1, True, 2.0, 2**64])
def test_min_pairs_contract(bad):
    panel, frame = fixture([1.0, -1.0], [0.1, 0.2])
    with pytest.raises(ValueError, match="min_pairs"):
        directional_scores(panel, frame, target_ids=["next"], min_pairs=bad)


@pytest.mark.parametrize("bad", [[], ["next", "next"], "next", [""]])
def test_target_ids_contract(bad):
    panel, frame = fixture([1.0, -1.0], [0.1, 0.2])
    with pytest.raises(ValueError, match="target_ids"):
        directional_scores(panel, frame, target_ids=bad, min_pairs=2)


def test_availability_after_decision_is_rejected():
    panel, frame = fixture([1.0, -1.0], [0.1, 0.2])
    late = panel.with_columns((pl.col("signal_available_at") + pl.duration(hours=1)).cast(UTC))
    with pytest.raises(ValueError):
        directional_scores(late, frame, target_ids=["next"], min_pairs=2)
