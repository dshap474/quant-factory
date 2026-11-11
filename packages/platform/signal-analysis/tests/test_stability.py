"""Independent weighted moments, explicit estimands, and stability coverage tests.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_stability.py``.
"""

# --------------------------------------------------------------------------- #
# Imports and supplied observations
# --------------------------------------------------------------------------- #
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import permutations

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.stability import summarize_metric_stability


def observations(values, *, assets=None, weights=None):
    n = len(values)
    return pl.DataFrame(
        {
            "observation_time": [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(n)],
            "asset": assets or ["A"] * n,
            "feature": ["x"] * n,
            "metric": ["MDA"] * n,
            "era": ["early" if i < 2 else "late" for i in range(n)],
            "value": values,
            "weight": weights if weights is not None else [1.0] * n,
        },
        schema={
            "observation_time": pl.Datetime("us", "UTC"),
            "asset": pl.String,
            "feature": pl.String,
            "metric": pl.String,
            "era": pl.String,
            "value": pl.Float64,
            "weight": pl.Float64,
        },
    )


def summarize(frame, groups=(), weighting="equal"):
    return summarize_metric_stability(
        frame, group_by=list(groups), weighting=weighting, sample_scope="supplied history"
    )


# --------------------------------------------------------------------------- #
# Hand-derived moments, grouping, and observed coverage
# --------------------------------------------------------------------------- #


def test_weighted_hand_answer_and_population_dispersion():
    frame = observations([1.0, 3.0], weights=[1.0, 3.0])
    row = summarize(frame, weighting="supplied").row(0, named=True)
    # Masses 1/4 and 3/4: mean=5/2; E[(X-mean)^2]=3/4.
    assert row["mean"] == pytest.approx(2.5, abs=1e-12, rel=0)
    assert row["std_population"] == pytest.approx(math.sqrt(3) / 2, abs=1e-12, rel=0)
    assert row["weight_sum"] == 4.0
    assert row["n_dates"] == row["n_assets"] * 2 == 2
    equal = summarize(frame).row(0, named=True)
    assert equal["mean"] == pytest.approx(2.0, abs=1e-12, rel=0)
    assert equal["std_population"] == pytest.approx(1.0, abs=1e-12, rel=0)
    assert_frame_equal(summarize(frame, weighting="supplied"), summarize(frame.reverse(), weighting="supplied"))
    rescaled = frame.with_columns(pl.col("weight") * 10)
    assert summarize(rescaled, weighting="supplied")["mean"][0] == row["mean"]


def test_asset_period_and_pooled_estimands_remain_distinct():
    frame = observations([1.0, 3.0, 10.0], assets=["A", "A", "B"])
    by_asset = summarize(frame, ["asset"])
    assert by_asset["mean"].to_list() == pytest.approx([2.0, 10.0], abs=1e-12, rel=0)
    assert summarize(frame)["mean"][0] == pytest.approx(14 / 3, abs=1e-12, rel=0)
    equal_asset = frame.with_columns(pl.Series("weight", [0.5, 0.5, 1.0]))
    assert summarize(equal_asset, weighting="supplied")["mean"][0] == pytest.approx(6.0, abs=1e-12, rel=0)
    assert summarize(frame, ["era"])["mean"].to_list() == pytest.approx([2.0, 10.0], abs=1e-12, rel=0)
    other_metric = frame.with_columns(pl.lit("SFI").alias("metric"), pl.col("value") * -1)
    both = summarize(pl.concat([frame, other_metric]))
    assert both["metric"].to_list() == ["MDA", "SFI"]
    assert both["mean"].to_list() == pytest.approx([14 / 3, -14 / 3], abs=1e-12, rel=0)


def test_missing_nonfinite_zero_weights_and_unobserved_dates():
    frame = observations([1.0, None, float("nan"), 5.0, 3.0], weights=[1.0, 0.0, 2.0, 0.0, 1.0])
    row = summarize(frame, weighting="supplied").row(0, named=True)
    assert [row[key] for key in ["n_total", "n_valid", "n_missing", "n_nonfinite", "n_zero_weight"]] == [5, 2, 1, 1, 1]
    assert row["n_dates"] == 2
    assert row["n_dates_supplied"] == 5
    assert row["mean"] == pytest.approx(2.0, abs=1e-12, rel=0)
    assert row["weight_sum"] == 2.0
    invalid = summarize(frame.slice(1, 3), weighting="supplied").row(0, named=True)
    assert invalid["status"] == "no_valid_observations"
    assert invalid["mean"] is invalid["std_population"] is invalid["first_valid_time"] is None
    assert invalid["n_dates"] == invalid["n_assets"] == 0
    assert invalid["weight_sum"] == 0.0
    # Deleting upstream rows reduces supplied coverage; no missing calendar inferred.
    sparse = summarize(frame.gather_every(4), weighting="supplied").row(0, named=True)
    assert sparse["n_dates_supplied"] == sparse["n_dates"] == 2


def test_extreme_finite_moments_against_decimal_oracle():
    values = [0.0] * 7 + [1e308] * 3
    with localcontext() as context:
        context.prec = 90
        numbers = [Decimal.from_float(value) for value in values]
        mean = sum(numbers) / Decimal(10)
        variance = sum((value - mean) ** 2 for value in numbers) / Decimal(10)
        expected_mean, expected_std = float(mean), float(variance.sqrt())
    row = summarize(observations(values)).row(0, named=True)
    assert row["status"] == "ok"
    assert row["mean"] == pytest.approx(expected_mean, abs=0, rel=1e-14)
    assert row["std_population"] == pytest.approx(expected_std, abs=0, rel=1e-14)
    opposite = summarize(observations([-1e308, 1e308])).row(0, named=True)
    assert opposite["mean"] == 0.0
    assert opposite["std_population"] == pytest.approx(1e308, abs=0, rel=1e-14)


def test_empty_schema_and_singleton():
    frame = observations([3.0])
    assert summarize(frame)["std_population"][0] == 0.0
    empty = summarize(frame.head(0), ["era"])
    assert empty.height == 0
    assert empty.schema["mean"] == pl.Float64
    assert empty.schema["n_dates"] == pl.UInt64
    assert empty.schema["first_valid_time"] == pl.Datetime("us", "UTC")


# --------------------------------------------------------------------------- #
# Identity and weight rejection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("weight", [None, -1.0, float("nan"), float("inf")])
def test_invalid_weight_rejected_even_when_value_missing(weight):
    with pytest.raises(ValueError):
        summarize(observations([None], weights=[weight]), weighting="supplied")


def test_invalid_identity_and_groups():
    frame = observations([1.0, 2.0])
    with pytest.raises(ValueError):
        summarize(pl.concat([frame, frame]))
    with pytest.raises(TypeError):
        summarize(frame.with_columns(pl.col("observation_time").dt.replace_time_zone(None)))
    with pytest.raises(ValueError):
        summarize(frame.with_columns(pl.lit(" ").alias("asset")))
    for groups in [["era", "era"], ["value"], ["feature"], ["weight"]]:
        with pytest.raises(ValueError):
            summarize(frame, groups)
    with pytest.raises(TypeError):
        summarize(frame, ["absent"])
    with pytest.raises(ArithmeticError):
        summarize(observations([1.0, 2.0], weights=[1e308, 1e308]), weighting="supplied")


def test_tiny_weight_retains_large_finite_moment_contributions():
    with localcontext() as context:
        context.prec = 90
        x = Decimal.from_float(1e308)
        wa, wb = Decimal.from_float(1e200), Decimal.from_float(1e-200)
        mean = x * wb / (wa + wb)
        variance = (wa * mean**2 + wb * (x - mean) ** 2) / (wa + wb)
        expected_mean, expected_std = float(mean), float(variance.sqrt())
    for values, weights in [([0.0, 1e308], [1e200, 1e-200]), ([1e308, 0.0], [1e-200, 1e200])]:
        row = summarize(observations(values, weights=weights), weighting="supplied").row(0, named=True)
        assert row["mean"] == pytest.approx(expected_mean, abs=0, rel=1e-14)
        assert row["std_population"] == pytest.approx(expected_std, abs=0, rel=1e-14)
        assert row["n_valid"] == 2


def test_tiny_weight_outlier_does_not_erase_bulk_deviations():
    # An origin at -1e100 rounds both other deltas to 1e100, losing a 1e40 SD.
    values, weights = [-1e100, 1e50, 0.0], [1e-200, 1.0, 1e-20]
    with localcontext() as context:
        context.prec = 700
        x = [Decimal.from_float(item) for item in values]
        w = [Decimal.from_float(item) for item in weights]
        mean = sum(a * b for a, b in zip(x, w, strict=True)) / sum(w)
        variance = sum(b * (a - mean) ** 2 for a, b in zip(x, w, strict=True)) / sum(w)
        expected_mean, expected_std = float(mean), float(variance.sqrt())
    for order in [[0, 1, 2], [2, 1, 0], [1, 0, 2]]:
        frame = observations([values[i] for i in order], weights=[weights[i] for i in order])
        row = summarize(frame, weighting="supplied").row(0, named=True)
        assert row["mean"] == pytest.approx(expected_mean, abs=0, rel=1e-14)
        assert row["std_population"] == pytest.approx(expected_std, abs=0, rel=1e-14)


def test_seeded_extreme_weight_and_value_strata_against_decimal():
    # Independent Decimal800 reference over a small repeatable exponent campaign.
    import numpy as np

    rng = np.random.default_rng(809)
    for _ in range(24):
        count = int(rng.integers(2, 9))
        values = [float(rng.choice([-1, 1])) * 10.0 ** int(rng.integers(-300, 301)) for _ in range(count)]
        weights = [10.0 ** int(rng.integers(-300, 301)) for _ in range(count)]
        with localcontext() as context:
            context.prec = 800
            x, w = list(map(Decimal.from_float, values)), list(map(Decimal.from_float, weights))
            mean = sum(a * b for a, b in zip(x, w, strict=True)) / sum(w)
            variance = sum(b * (a - mean) ** 2 for a, b in zip(x, w, strict=True)) / sum(w)
            expected_mean, expected_std = float(mean), float(variance.sqrt())
        row = summarize(observations(values, weights=weights), weighting="supplied").row(0, named=True)
        assert row["mean"] == pytest.approx(expected_mean, abs=0, rel=1e-12)
        assert row["std_population"] == pytest.approx(expected_std, abs=0, rel=1e-12)


@pytest.mark.parametrize("exponent", [0, -1000])
def test_overflowing_outlier_preserves_influential_spacing(exponent):
    # Power-of-two scaling changes units exactly. A vanishing-weight outlier
    # must not erase the adjacent-float spacing between the two major weights.
    values = [math.ldexp(x, exponent) for x in [1e308, math.nextafter(1e308, math.inf), -1e308]]
    weights = [1.0, 1.0, 1e-100]
    expected = []
    for precision in [800, 1600]:
        with localcontext() as context:
            context.prec = precision
            x, w = list(map(Decimal.from_float, values)), list(map(Decimal.from_float, weights))
            mean = sum(a * b for a, b in zip(x, w, strict=True)) / sum(w)
            std = (sum(b * (a - mean) ** 2 for a, b in zip(x, w, strict=True)) / sum(w)).sqrt()
            expected.append((float(mean), float(std)))
    assert expected[0] == expected[1]
    for order in permutations(range(3)):
        row = summarize(
            observations([values[i] for i in order], weights=[weights[i] for i in order]), weighting="supplied"
        ).row(0, named=True)
        assert row["status"] == "ok"
        assert row["mean"] == pytest.approx(expected[0][0], abs=0, rel=1e-14)
        assert row["std_population"] == pytest.approx(expected[0][1], abs=0, rel=1e-14)


@pytest.mark.parametrize(
    "values,weights",
    [
        ([1e308, -5e307, 1.0], [1.0, 2.0, 1.0]),
        ([float.fromhex("0x1.fffffffffffffp+1023")] * 3, [1.0] * 3),
        ([math.ulp(0.0)] * 2, [1.0, 1.0]),
        ([math.ulp(0.0), 2 * math.ulp(0.0)], [1.0, 1.0]),
        ([float.fromhex("0x1.fffffffffffffp+1023"), -float.fromhex("0x1.fffffffffffffp+1023")] * 3, [1.0] * 6),
        ([0.0, float.fromhex("0x1.fffffffffffffp+1023")], [float.fromhex("0x1.fffffffffffffp+1023"), math.ulp(0.0)]),
    ],
)
def test_weighted_extremes_against_independent_pair_distance_variance(values, weights):
    x, w = list(map(Fraction, values)), list(map(Fraction, weights))
    total = sum(w)
    expected_mean = float(sum(a * b for a, b in zip(x, w, strict=True)) / total)
    # Pair-distance identity is independent of production's raw-moment reduction.
    variance = sum(w[i] * w[j] * (x[i] - x[j]) ** 2 for i in range(len(x)) for j in range(i)) / total**2
    if len(x) == 2 and w[0] == w[1]:
        # This exact rational SD includes the halfway subnormal ties-to-even case.
        expected_std = float(abs(x[0] - x[1]) / 2)
    else:
        roots = []
        for precision in [800, 1600]:
            with localcontext() as context:
                context.prec = precision
                roots.append(float((Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()))
        assert roots[0] == roots[1]
        expected_std = roots[0]
    for order in [list(range(len(x))), list(reversed(range(len(x))))]:
        row = summarize(
            observations([values[i] for i in order], weights=[weights[i] for i in order]), weighting="supplied"
        ).row(0, named=True)
        assert row["status"] == "ok"
        assert row["mean"] == expected_mean
        assert row["std_population"] == expected_std
