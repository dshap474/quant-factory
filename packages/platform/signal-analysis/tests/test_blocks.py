"""Known-answer, invariant, and contract tests for calendar-anchored blocks and the lag diagnostic.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_blocks.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone
from fractions import Fraction
from math import sqrt

import numpy as np
import polars as pl
import pytest

from signal_analysis.blocks import block_means, block_samples, first_insignificant_lag
from signal_analysis.inference import moving_block_mean, newey_west_mean

UTC = pl.Datetime("us", "UTC")
ORIGIN = datetime(2025, 1, 1, tzinfo=timezone.utc)


def calendar(n):
    return pl.DataFrame(
        {"decision_time": [ORIGIN + timedelta(days=i) for i in range(n)]}, schema={"decision_time": UTC}
    )


def samples(values, *, skip=()):
    dates = [ORIGIN + timedelta(days=i) for i in range(len(values)) if i not in skip]
    kept = [value for i, value in enumerate(values) if i not in skip]
    return pl.DataFrame({"decision_time": dates, "value": kept}, schema={"decision_time": UTC, "value": pl.Float64})


def blocks(values, *, n=None, skip=(), **overrides):
    settings = dict(calendar_id="daily", inferential_unit="ic", block_length=4, min_coverage=0.75)
    settings.update(overrides)
    return block_means(samples(values, skip=skip), calendar=calendar(n or len(values)), **settings)


# --------------------------------------------------------------------------- #
# Block means: known answers
# --------------------------------------------------------------------------- #


def test_twelve_days_four_day_blocks_one_missing_day_keeps_edges():
    # Day index 2 is absent from the samples but present in the calendar.
    values = [float(v) for v in range(1, 13)]
    result = blocks(values, skip={2}, n=12)
    assert result["status"].to_list() == ["ok", "ok", "ok"]
    assert result["block_start"].to_list() == [ORIGIN, ORIGIN + timedelta(days=4), ORIGIN + timedelta(days=8)]
    assert result["block_end"].to_list() == [
        ORIGIN + timedelta(days=3),
        ORIGIN + timedelta(days=7),
        ORIGIN + timedelta(days=11),
    ]
    first = result.row(0, named=True)
    assert (first["n_expected"], first["n_observed"], first["n_valid"], first["n_missing"]) == (4, 3, 3, 1)
    assert first["mean"] == float(Fraction(1 + 2 + 4, 3))
    assert result["mean"].to_list()[1:] == [6.5, 10.5]
    assert result["block_length"].to_list() == [4, 4, 4]
    assert result["calendar_id"].to_list() == ["daily"] * 3


def test_block_with_one_of_four_is_insufficient_coverage_and_has_no_mean():
    result = blocks([float(v) for v in range(8)], skip={0, 1, 2}, n=8, min_coverage=0.5)
    assert result["status"].to_list() == ["insufficient_coverage", "ok"]
    assert result["mean"].to_list()[0] is None
    assert result.row(0, named=True)["n_valid"] == 1


def test_default_coverage_requires_every_session():
    result = blocks([float(v) for v in range(8)], skip={5}, n=8, min_coverage=1.0)
    assert result["status"].to_list() == ["ok", "insufficient_coverage"]


def test_trailing_partial_block_is_never_ok():
    result = blocks([float(v) for v in range(10)], n=10)
    assert result["status"].to_list() == ["ok", "ok", "incomplete_trailing"]
    last = result.row(2, named=True)
    assert last["n_expected"] == 2 and last["mean"] is None
    assert last["block_start"] == ORIGIN + timedelta(days=8)


def test_all_missing_block_is_empty():
    result = blocks([float(v) for v in range(8)], skip={0, 1, 2, 3}, n=8, min_coverage=0.25)
    assert result["status"].to_list() == ["empty", "ok"]


def test_nonfinite_values_are_counted_and_excluded_not_averaged():
    result = blocks([1.0, float("nan"), 3.0, float("inf")], min_coverage=0.5)
    row = result.row(0, named=True)
    assert row["status"] == "ok"
    assert (row["n_observed"], row["n_valid"], row["n_nonfinite"]) == (4, 2, 2)
    assert row["mean"] == 2.0


def test_default_block_length_is_thirty_sessions():
    result = block_means(samples([1.0] * 90), calendar=calendar(90), calendar_id="d", inferential_unit="u")
    assert result.height == 3 and result["block_length"].to_list() == [30, 30, 30]
    assert result["status"].to_list() == ["ok"] * 3


def test_mean_retains_cancellation_residual():
    result = blocks([1e308, 1.0, -1e308, 0.0], min_coverage=0.5)
    assert result["mean"].to_list() == [0.25]


def test_calendar_sessions_are_units_not_elapsed_days():
    # Weekend gaps in the calendar do not create empty blocks: blocks count sessions.
    dates = [ORIGIN + timedelta(days=d) for d in (0, 1, 4, 5, 6, 7)]
    cal = pl.DataFrame({"decision_time": dates}, schema={"decision_time": UTC})
    frame = cal.with_columns(pl.Series("value", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
    result = block_means(frame, calendar=cal, calendar_id="sessions", inferential_unit="u", block_length=3)
    assert result["mean"].to_list() == [2.0, 5.0]
    assert result["block_end"].to_list()[0] == ORIGIN + timedelta(days=4)


# --------------------------------------------------------------------------- #
# Block means: contracts
# --------------------------------------------------------------------------- #


def test_off_calendar_sample_rejected():
    with pytest.raises(ValueError, match="outside the declared calendar"):
        block_means(samples([1.0] * 5), calendar=calendar(4), calendar_id="d", inferential_unit="u", block_length=2)


@pytest.mark.parametrize("length", [0, True, 2.0])
def test_block_length_must_be_positive_integer(length):
    with pytest.raises((TypeError, ValueError)):
        blocks([1.0] * 4, block_length=length)


@pytest.mark.parametrize("coverage", [0.0, 1.5, float("nan"), True])
def test_min_coverage_bounds(coverage):
    with pytest.raises((TypeError, ValueError)):
        blocks([1.0] * 4, min_coverage=coverage)


def test_naive_clock_and_duplicate_dates_rejected():
    naive = samples([1.0] * 4).with_columns(pl.col("decision_time").dt.replace_time_zone(None))
    with pytest.raises(TypeError):
        block_means(naive, calendar=calendar(4), calendar_id="d", inferential_unit="u")
    dup = pl.concat([samples([1.0] * 4), samples([2.0])])
    with pytest.raises(ValueError, match="duplicate"):
        block_means(dup, calendar=calendar(4), calendar_id="d", inferential_unit="u")


def test_input_order_and_extra_columns_do_not_matter():
    frame = (
        samples([float(v) for v in range(8)]).with_columns(pl.lit("x").alias("extra")).sort("value", descending=True)
    )
    result = block_means(frame, calendar=calendar(8).reverse(), calendar_id="d", inferential_unit="u", block_length=4)
    assert result["mean"].to_list() == [1.5, 5.5]


# --------------------------------------------------------------------------- #
# Block samples and hand-off to the inference operations
# --------------------------------------------------------------------------- #


def test_block_samples_keep_only_ok_blocks_and_return_matching_calendar():
    result = blocks([float(v) for v in range(10)], skip={5, 6}, n=10)
    sample, cal = block_samples(result)
    assert sample["decision_time"].to_list() == [ORIGIN]
    assert sample["value"].to_list() == [1.5]
    assert cal.equals(sample.select("decision_time"))


def test_paired_block_samples_use_both_ok_blocks_and_identical_edges():
    candidate = blocks([float(v) for v in range(12)], n=12)
    baseline = blocks([float(v) * 2 for v in range(12)], skip={4}, n=12, min_coverage=1.0)
    sample, cal = block_samples(candidate, baseline=baseline)
    assert sample.columns == ["decision_time", "candidate", "baseline"]
    assert sample["decision_time"].to_list() == [ORIGIN, ORIGIN + timedelta(days=8)]
    assert sample["candidate"].to_list() == [1.5, 9.5]
    assert sample["baseline"].to_list() == [3.0, 19.0]
    assert cal.height == 2
    shifted = blocks([float(v) for v in range(12)], n=12, block_length=6)
    with pytest.raises(ValueError, match="identical block edges"):
        block_samples(candidate, baseline=shifted)


def test_block_samples_rejects_non_block_frames():
    with pytest.raises(TypeError):
        block_samples(samples([1.0]))


def test_hac_lag_zero_on_blocks_matches_iid_standard_error():
    values = [float(v) for v in (1, 4, 2, 8, 5, 7, 3, 6, 9, 0, 4, 4)]
    result = blocks(values, n=12, block_length=3)
    sample, cal = block_samples(result)
    row = newey_west_mean(sample, calendar=cal, calendar_id="b", inferential_unit="u", max_lag=0, confidence_level=0.95)
    row = row.row(0, named=True)
    means = [Fraction(sum(values[i : i + 3])) / 3 for i in range(0, 12, 3)]
    grand = sum(means) / 4
    variance = sum((m - grand) ** 2 for m in means) / 4
    assert row["status"] == "ok" and row["n_valid"] == 4
    assert row["estimate"] == pytest.approx(float(grand), abs=1e-12)
    assert row["standard_error"] == pytest.approx(sqrt(float(variance) / 4), abs=1e-12)


def test_moving_block_length_one_over_block_means_is_always_admissible():
    result = blocks([float(v) for v in range(20)], n=20, block_length=5)
    sample, cal = block_samples(result)
    row = moving_block_mean(
        sample,
        calendar=cal,
        calendar_id="b",
        inferential_unit="u",
        block_length=1,
        n_resamples=400,
        seed=3,
        confidence_level=0.9,
    ).row(0, named=True)
    assert row["status"] == "ok" and row["n_valid"] == 4
    assert row["ci_lower"] < row["estimate"] < row["ci_upper"]


# --------------------------------------------------------------------------- #
# Decorrelation lag
# --------------------------------------------------------------------------- #


def test_acf_known_answer_for_one_to_six():
    # Deviations (-2.5,-1.5,-0.5,0.5,1.5,2.5), denominator 17.5.
    x = [Fraction(v) for v in range(1, 7)]
    m = sum(x) / 6
    d = [v - m for v in x]
    denom = sum(v * v for v in d)
    expected = [sum(d[i] * d[i + lag] for i in range(6 - lag)) / denom for lag in (1, 2, 3)]
    result = first_insignificant_lag([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], max_lag=3)
    assert result.n_obs == 6 and result.band == pytest.approx(1.96 / sqrt(6))
    assert list(result.acf) == pytest.approx([float(e) for e in expected], abs=1e-15)
    assert expected[0] == Fraction(1, 2)


def test_persistent_series_reports_lag_beyond_one_and_white_series_lag_one():
    rng = np.random.Generator(np.random.PCG64(11))
    noise = rng.standard_normal(400)
    persistent = np.empty(400)
    persistent[0] = noise[0]
    for t in range(1, 400):
        persistent[t] = 0.9 * persistent[t - 1] + noise[t]
    slow = first_insignificant_lag(persistent, max_lag=60)
    assert slow.status == "ok" and slow.lag > 1
    quick = first_insignificant_lag(noise, max_lag=60)
    assert abs(quick.acf[0]) < quick.band  # precondition for this seed
    assert quick.lag == 1 and quick.status == "ok"


def test_no_insignificant_lag_within_max_lag_is_unavailable_with_acf_retained():
    persistent = np.cumsum(np.ones(50))
    result = first_insignificant_lag(persistent, max_lag=3)
    assert result.status == "unavailable_no_insignificant_lag" and result.lag is None
    assert len(result.acf) == 3


def test_short_constant_and_nonfinite_series_are_unavailable():
    assert first_insignificant_lag([1.0, 2.0, 3.0], max_lag=3).status == "unavailable_insufficient_observations"
    assert first_insignificant_lag([5.0] * 10, max_lag=2).status == "unavailable_degenerate"
    assert first_insignificant_lag([1.0, float("nan"), 3.0, 4.0], max_lag=1).status == "unavailable_nonfinite"


def test_lag_is_scale_and_location_invariant():
    base = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0])
    a = first_insignificant_lag(base, max_lag=4)
    b = first_insignificant_lag(1e200 * base + 7e200, max_lag=4)
    assert list(a.acf) == pytest.approx(list(b.acf), abs=1e-12)
    assert a.lag == b.lag


@pytest.mark.parametrize("lag", [0, True, 2.5])
def test_max_lag_must_be_positive_integer(lag):
    with pytest.raises((TypeError, ValueError)):
        first_insignificant_lag([1.0, 2.0, 3.0, 4.0], max_lag=lag)
