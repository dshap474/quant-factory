"""Independent rational, enumeration, invariant, and process tests of inference.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_inference.py``.
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
from math import ceil, sqrt
from statistics import NormalDist

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.inference import (
    moving_block_mean,
    moving_block_paired_difference,
    newey_west_mean,
    newey_west_paired_difference,
)

# --------------------------------------------------------------------------- #
# Fixtures and independent exact oracles
# --------------------------------------------------------------------------- #


def frames(values):
    dates = [datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(len(values))]
    calendar = pl.DataFrame({"decision_time": dates}, schema={"decision_time": pl.Datetime("us", "UTC")})
    return calendar.with_columns(pl.Series("value", values, dtype=pl.Float64)), calendar


def settings(calendar):
    return dict(calendar=calendar, calendar_id="explicit_daily", inferential_unit="dated_ic", confidence_level=0.95)


def hac(values, lag=1):
    sample, calendar = frames(values)
    return newey_west_mean(sample, **settings(calendar), max_lag=lag).row(0, named=True)


def bootstrap(values, length=2, repeats=999, seed=17):
    sample, calendar = frames(values)
    return moving_block_mean(sample, **settings(calendar), block_length=length, n_resamples=repeats, seed=seed).row(
        0, named=True
    )


def rational_hac_variance(values, lag):
    # Independent all-pairs covariance quadratic form, using exact arithmetic.
    # Production sums one triangle by lag; this oracle forms every matrix cell.
    n = len(values)
    mean = sum(map(Fraction, values)) / n
    residuals = [Fraction(value) - mean for value in values]
    return (
        sum(
            residuals[i] * residuals[j] * max(Fraction(0), 1 - Fraction(abs(i - j), lag + 1))
            for i in range(n)
            for j in range(n)
        )
        / n**2
    )


def enumerated_bootstrap(values, length):
    # Enumerate the original resampled observation tuples, not block-mean
    # variance or a random sampler. This is feasible only for tiny fixtures.
    n = len(values)
    draws = [
        sum(Fraction(values[start + offset]) for start in starts for offset in range(length)) / n
        for starts in product(range(n - length + 1), repeat=n // length)
    ]
    center = sum(draws) / len(draws)
    variance = sum((draw - center) ** 2 for draw in draws) / len(draws)
    return center, variance


# --------------------------------------------------------------------------- #
# Exact anchors and transformations
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lag", [0, 1, 2, 3])
@pytest.mark.parametrize("values", [[1, 2, 3, 4], [-3, 2, 0, 7], [0, 0, 0, 4]])
def test_hac_rational_quadratic_form(values, lag):
    row = hac(values, lag)
    expected = rational_hac_variance(values, lag)
    assert row["standard_error"] ** 2 == pytest.approx(float(expected), abs=1e-12, rel=0)
    assert row["estimate"] == pytest.approx(sum(values) / len(values), abs=1e-12, rel=0)
    radius = NormalDist().inv_cdf(0.975) * sqrt(expected)
    assert row["ci_lower"] == pytest.approx(row["estimate"] - radius, abs=1e-12, rel=0)
    assert row["ci_upper"] == pytest.approx(row["estimate"] + radius, abs=1e-12, rel=0)
    assert row["status"] == "ok"


@pytest.mark.parametrize("length", [1, 2])
@pytest.mark.parametrize("values", [[1, 2, 3, 4], [0, 0, 0, 4], [-3, 2, 0, 7]])
def test_bootstrap_exact_enumeration(values, length):
    _, variance = enumerated_bootstrap(values, length)
    row = bootstrap(values, length)
    assert row["standard_error"] ** 2 == pytest.approx(float(variance), abs=1e-12, rel=0)
    assert row["standard_error_kind"] == "exact_conditional_block_mean_variance"
    assert row["quantile_method"] == "inverted_cdf"


def test_nonwrapping_edge_centering_is_deliberate():
    center, variance = enumerated_bootstrap([0, 0, 0, 4], 2)
    assert center == Fraction(2, 3)
    assert variance == Fraction(4, 9)
    # Conditional support of T* is {0,1,2}; both tail masses exceed 2.5%.
    # T=1, so basic inversion of T*-T gives [0,2]. Centering by E*T instead
    # would incorrectly yield [-1/3,5/3]. No Monte Carlo precision claim here.
    row = bootstrap([0, 0, 0, 4], repeats=4000)
    assert row["estimate"] == 1
    assert row["ci_lower"] == 0
    assert row["ci_upper"] == 2


def test_hac_shift_scale_and_time_reversal():
    values = np.array([-3.0, 1, 7, -2, 4, 9])
    base = hac(values.tolist(), 3)
    for transformed, scale, shift in [(values + 50, 1, 50), (-3 * values, -3, 0)]:
        row = hac(transformed.tolist(), 3)
        assert row["estimate"] == pytest.approx(base["estimate"] * scale + shift, abs=1e-12, rel=0)
        assert row["standard_error"] == pytest.approx(base["standard_error"] * abs(scale), abs=1e-12, rel=0)
    reversed_row = hac(values[::-1].tolist(), 3)
    assert reversed_row["standard_error"] == pytest.approx(base["standard_error"], abs=1e-12, rel=0)


@pytest.mark.parametrize("method", ["hac", "bootstrap"])
def test_paired_common_component_and_swap(method):
    differences = [1.0, -2, 3, 0, 2, 8]
    common = [100.0, -200, 300, 50, 700, -80]
    sample, calendar = frames(differences)
    paired = sample.select("decision_time").with_columns(
        pl.Series("candidate", [a + b for a, b in zip(differences, common, strict=True)]),
        pl.Series("baseline", common),
    )
    if method == "hac":
        single_fn, paired_fn, tuning = newey_west_mean, newey_west_paired_difference, dict(max_lag=2)
    else:
        single_fn, paired_fn = moving_block_mean, moving_block_paired_difference
        tuning = dict(block_length=2, n_resamples=999, seed=17)
    expected = single_fn(sample, **settings(calendar), **tuning).row(0, named=True)
    actual = paired_fn(paired, **settings(calendar), **tuning).row(0, named=True)
    swap = paired_fn(
        paired.rename({"candidate": "baseline", "baseline": "candidate"}), **settings(calendar), **tuning
    ).row(0, named=True)
    for field in ("estimate", "standard_error", "ci_lower", "ci_upper"):
        assert actual[field] == pytest.approx(expected[field], abs=1e-12, rel=0)
    assert swap["estimate"] == -actual["estimate"]
    assert swap["standard_error"] == actual["standard_error"]
    assert swap["ci_lower"] == pytest.approx(-actual["ci_upper"], abs=1e-12, rel=0)
    assert swap["ci_upper"] == pytest.approx(-actual["ci_lower"], abs=1e-12, rel=0)


# --------------------------------------------------------------------------- #
# Coverage, unavailable cases, and boundary validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method", [newey_west_mean, moving_block_mean])
def test_gaps_never_collapse_and_input_order_does_not_matter(method):
    sample, calendar = frames([1.0, 2, 3, 4])
    tuning = dict(max_lag=1) if method is newey_west_mean else dict(block_length=2, n_resamples=99, seed=3)
    gapped = sample.filter(pl.col("value") != 2)
    result = method(gapped, **settings(calendar), **tuning)
    row = result.row(0, named=True)
    assert row["status"] == "unavailable_gap_or_missing"
    assert (row["n_expected"], row["n_observed"], row["n_valid"], row["n_missing"]) == (4, 3, 3, 1)
    assert row["estimate"] == pytest.approx(8 / 3, abs=1e-12, rel=0)
    assert row["ci_lower"] is row["ci_upper"] is None
    assert_frame_equal(result, method(gapped.reverse(), **settings(calendar.reverse()), **tuning))
    # Missing value at the same expected date has identical inferential status.
    nulls = sample.with_columns(pl.when(pl.col("value") == 2).then(None).otherwise("value").alias("value"))
    assert method(nulls, **settings(calendar), **tuning)["status"][0] == row["status"]


def test_missing_nonfinite_coverage_precedence_and_pair_overflow():
    sample, calendar = frames([1.0, None, float("nan"), float("inf"), -3])
    row = newey_west_mean(sample, **settings(calendar), max_lag=1).row(0, named=True)
    assert (row["n_valid"], row["n_missing"], row["n_nonfinite"]) == (2, 1, 2)
    assert row["n_expected"] == row["n_valid"] + row["n_missing"] + row["n_nonfinite"]
    sample, calendar = frames([1e308, 0])
    paired = sample.rename({"value": "candidate"}).with_columns(pl.Series("baseline", [-1e308, 0]))
    row = newey_west_paired_difference(paired, **settings(calendar), max_lag=0).row(0, named=True)
    assert row["status"] == "unavailable_numerical"
    assert row["estimate"] is None


@pytest.mark.parametrize("values", [[], [1.0]])
def test_insufficient_observations_and_typed_results(values):
    row = hac(values, 0)
    assert row["status"] == "unavailable_insufficient_observations"
    assert row["n_valid"] == len(values)
    sample, calendar = frames(values)
    result = newey_west_mean(sample, **settings(calendar), max_lag=0)
    assert result.schema["n_valid"] == pl.UInt64
    assert result.schema["start_time"] == pl.Datetime("us", "UTC")


def test_degenerate_and_bootstrap_resolution():
    assert hac([3.0] * 4)["status"] == "unavailable_degenerate"
    assert bootstrap([3.0] * 4)["status"] == "unavailable_degenerate"
    # Alternation has constant length-two block means despite nonconstant data.
    assert bootstrap([1.0, -1, 1, -1])["status"] == "unavailable_degenerate"
    row = bootstrap([1.0, 2, 3, 4], repeats=20)
    assert row["status"] == "unavailable_insufficient_resamples"
    assert row["standard_error"] is not None
    assert row["ci_lower"] is None
    assert row["expected_tail_draws"] == pytest.approx(0.5, abs=1e-14, rel=0)
    assert hac([1.0, 2], lag=2)["status"] == "unavailable_insufficient_observations"


@pytest.mark.parametrize("length", [3, 4, 5])
def test_no_bootstrap_trim_wrap_or_padding(length):
    with pytest.raises(ValueError, match="divisible"):
        bootstrap([1.0, 2, 3, 4], length)


@pytest.mark.parametrize("value", [True, 1.5, -1, 2**64])
def test_invalid_hac_lag(value):
    with pytest.raises((TypeError, ValueError)):
        hac([1.0, 2, 3, 4], value)


@pytest.mark.parametrize("confidence", [True, 0, 1, float("nan"), float("inf")])
def test_invalid_confidence(confidence):
    sample, calendar = frames([1.0, 2])
    args = settings(calendar) | {"confidence_level": confidence}
    with pytest.raises((TypeError, ValueError)):
        newey_west_mean(sample, **args, max_lag=0)


def test_schema_identity_and_grid_validation():
    sample, calendar = frames([1.0, 2])
    for bad in [
        sample.with_columns(pl.col("value").cast(pl.Int64)),
        sample.with_columns(pl.col("decision_time").dt.replace_time_zone(None)),
    ]:
        with pytest.raises(TypeError):
            newey_west_mean(bad, **settings(calendar), max_lag=0)
    with pytest.raises(ValueError, match="duplicate"):
        newey_west_mean(pl.concat([sample, sample]), **settings(calendar), max_lag=0)
    with pytest.raises(ValueError, match="outside"):
        newey_west_mean(sample, **settings(calendar.head(1)), max_lag=0)
    with pytest.raises(ValueError):
        newey_west_mean(sample, **(settings(calendar) | {"calendar_id": " daily "}), max_lag=0)


def test_determinism_rng_isolation_and_declared_session_calendar():
    sample, calendar = frames([1.0, 2, 3, 4])
    # Calendar declares consecutive *sessions* across a weekend. No elapsed-time
    # cadence is inferred; Friday-to-Monday can be a session lag of one.
    shift = pl.when(pl.col("decision_time").dt.day() >= 3).then(pl.duration(days=2)).otherwise(pl.duration(days=0))
    sample = sample.with_columns(pl.col("decision_time") + shift)
    calendar = sample.select("decision_time")
    kwargs = settings(calendar) | dict(block_length=2, n_resamples=99, seed=7)
    np.random.seed(123)
    state = np.random.get_state()
    first = moving_block_mean(sample, **kwargs)
    after = np.random.get_state()
    assert np.array_equal(state[1], after[1]) and state[2:] == after[2:]
    assert_frame_equal(first, moving_block_mean(sample.reverse(), **kwargs))
    assert first["status"][0] == "ok"


def test_extreme_scale_and_large_location():
    row = hac([1e308, 1e308, -1e308, -1e308], 0)
    assert row["status"] == "ok"
    assert row["estimate"] == 0
    assert row["standard_error"] == pytest.approx(5e307, rel=1e-14)
    base = hac([0.0, 2, 4, 8], 1)
    shifted = hac([1e16, 1e16 + 2, 1e16 + 4, 1e16 + 8], 1)
    assert shifted["standard_error"] == pytest.approx(base["standard_error"], abs=1e-12, rel=0)
    tiny = hac([1e-300, 2e-300, 3e-300, 4e-300], 1)
    assert tiny["standard_error"] / 1e-300 == pytest.approx(hac([1, 2, 3, 4], 1)["standard_error"], abs=1e-12, rel=0)


# --------------------------------------------------------------------------- #
# Cancellation regressions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("residual", [1.0, 1e-308])
def test_mean_retains_tiny_cancellation_residual(residual):
    sample, calendar = frames([1e308, residual, -1e308])
    row = newey_west_mean(sample, **(settings(calendar) | {"confidence_level": 0.5}), max_lag=0).row(0, named=True)
    assert row["estimate"] == residual / 3
    assert row["status"] == "ok"


def test_mean_does_not_lose_subnormal_constant_or_overflow_sum():
    smallest = float.fromhex("0x0.0000000000001p-1022")
    assert hac([smallest, smallest], 0)["estimate"] == smallest
    assert hac([1e308, 1e308], 0)["estimate"] == 1e308
    # An unscaled compensated accumulation overflows in this input order;
    # division before accumulation would erase its subnormal residual.
    row = hac([1e308, 1e308, -1e308, -1e308, smallest], 0)
    assert row["status"] == "unavailable_numerical"
    assert row["estimate"] is None


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize(
    "values,length",
    [
        ([1.0, -1.0, np.nextafter(1.0, 2.0), -1.0], 2),
        ([1e16, -1e16, 1.0, 1e16, -1e16, 2.0], 3),
        ([1.0, -1.0, 1e-16, 1.0, -1.0, 2e-16], 3),
        ([1e16, -1e16, 1e16, -9999999999999998.0], 2),
        ([1e308, -1e308, 1e-308, 1e308, -1e308, 2e-308], 3),
        ([1e308, 1e308, -1e308, -1e308], 2),
        ([1e16, 1e16 + 2, 1e16 + 4, 1e16 + 8], 2),
    ],
)
def test_bootstrap_cancellation_against_resampled_observation_oracle(values, length, paired):
    # Enumerate concatenated *observations* in Fraction arithmetic, independently
    # of the production block-statistic algorithm. Decimal sqrt avoids squaring
    # Float64 under/overflow. 1e-14 covers the final norm and subnormal rounding;
    # integer-order-statistic CI endpoints require only a final float rounding.
    _, variance = enumerated_bootstrap(values, length)
    with localcontext() as context:
        context.prec = 800
        expected_se = float((Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt())
    n, repeats, seed = len(values), 200, 13
    exact_mean = sum(map(Fraction, values)) / n
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = sorted(
        sum(
            Fraction(values[start + offset])
            for start in rng.integers(0, n - length + 1, n // length)
            for offset in range(length)
        )
        / n
        for _ in range(repeats)
    )
    tail = (1 - 0.95) / 2
    expected_low = float(2 * exact_mean - draws[ceil((1 - tail) * repeats) - 1])
    expected_high = float(2 * exact_mean - draws[ceil(tail * repeats) - 1])
    sample, calendar = frames(values)
    operation = moving_block_mean
    if paired:
        sample = sample.rename({"value": "candidate"}).with_columns(pl.lit(0.0).alias("baseline"))
        operation = moving_block_paired_difference
    row = operation(sample, **settings(calendar), block_length=length, n_resamples=repeats, seed=seed).row(
        0, named=True
    )
    assert row["status"] == "ok"
    assert row["estimate"] == float(exact_mean)
    assert row["standard_error"] == pytest.approx(expected_se, abs=0, rel=1e-14)
    assert row["ci_lower"] == expected_low
    assert row["ci_upper"] == expected_high


def test_nonzero_bootstrap_se_below_float_domain_is_numerically_unavailable():
    smallest = float.fromhex("0x0.0000000000001p-1022")
    # Exact block means are (smallest/2, smallest/2, 0), so SE=smallest/6.
    row = bootstrap([0.0, smallest, 0.0, 0.0], length=2)
    assert row["status"] == "unavailable_numerical"
    assert row["standard_error"] is row["ci_lower"] is row["ci_upper"] is None


def test_bootstrap_exact_interval_overflow_is_numerically_unavailable():
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    row = bootstrap([largest, largest, largest, 0.0], length=1, repeats=4000)
    # T=3*largest/4 and the lower resampled tail is largest/4, so basic
    # inversion's upper bound is 5*largest/4, outside the finite output domain.
    assert row["status"] == "unavailable_numerical"
    assert row["standard_error"] > 0
    assert row["ci_lower"] is row["ci_upper"] is None


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("method", ["hac", "bootstrap"])
def test_maximum_constant_mean_does_not_overflow_fallback(paired, method):
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    sample, calendar = frames([largest] * 3)
    if paired:
        sample = sample.rename({"value": "candidate"}).with_columns(pl.lit(0.0).alias("baseline"))
    if method == "hac":
        operation = newey_west_paired_difference if paired else newey_west_mean
        tuning = dict(max_lag=0)
    else:
        operation = moving_block_paired_difference if paired else moving_block_mean
        tuning = dict(block_length=1, n_resamples=100, seed=1)
    row = operation(sample, **settings(calendar), **tuning).row(0, named=True)
    assert row["estimate"] == largest
    assert row["status"] == "unavailable_degenerate"


# --------------------------------------------------------------------------- #
# Additional boundary regressions
# --------------------------------------------------------------------------- #


def test_nonzero_uncertainty_cannot_round_to_valid_zero_width_interval():
    sample, calendar = frames([1e16, 1e16 + 2])
    row = newey_west_mean(sample, **(settings(calendar) | {"confidence_level": 0.1}), max_lag=0).row(0, named=True)
    assert row["status"] == "unavailable_numerical"
    assert row["ci_lower"] is row["ci_upper"] is None


def test_pair_missing_precedence_and_accounting():
    sample, calendar = frames([1.0, None, float("nan"), 2])
    paired = sample.rename({"value": "candidate"}).with_columns(pl.Series("baseline", [0.0, float("inf"), 0, None]))
    row = moving_block_paired_difference(paired, **settings(calendar), block_length=2, n_resamples=99, seed=0).row(
        0, named=True
    )
    assert row["status"] == "unavailable_gap_or_missing"
    assert (row["n_valid"], row["n_missing"], row["n_nonfinite"]) == (1, 2, 1)
    assert row["estimate"] == 1


@pytest.mark.parametrize("tuning", [{"block_length": True}, {"n_resamples": 1}, {"seed": -1}, {"seed": True}])
def test_bootstrap_setting_validation(tuning):
    sample, calendar = frames([1.0, 2, 3, 4])
    with pytest.raises((TypeError, ValueError)):
        moving_block_mean(sample, **settings(calendar), **(dict(block_length=2, n_resamples=99, seed=0) | tuning))


# --------------------------------------------------------------------------- #
# Seeded process calibration: scoped evidence, not a universal coverage proof
# --------------------------------------------------------------------------- #


def test_stationary_ar1_ensemble_matches_analytic_mean_variance():
    # Stationary AR(1), phi=.5, innovation variance=.75 -> marginal variance1.
    # Exact finite-n mean variance is obtained by counting all covariance pairs.
    n, runs, phi = 512, 160, 0.5
    theoretical = (n + 2 * sum((n - lag) * phi**lag for lag in range(1, n))) / n**2
    rng = np.random.Generator(np.random.PCG64(7291))
    estimated, covered = [], 0
    for _ in range(runs):
        x = np.empty(n)
        x[0] = rng.normal()
        innovations = rng.normal(scale=sqrt(0.75), size=n - 1)
        for t in range(1, n):
            x[t] = phi * x[t - 1] + innovations[t - 1]
        row = hac(x.tolist(), 12)
        estimated.append(row["standard_error"] ** 2)
        covered += row["ci_lower"] <= 0 <= row["ci_upper"]
    # Explicit broad bands allow finite-lag bias and Monte Carlo error; the
    # independent exact oracle above carries transcription-level precision.
    assert 0.72 < np.mean(estimated) / theoretical < 1.18
    assert 0.85 < covered / runs <= 1.0
