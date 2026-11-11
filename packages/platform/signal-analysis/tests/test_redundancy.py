"""Known-answer and coverage tests for public feature redundancy diagnostics.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_redundancy.py``.
"""

# --------------------------------------------------------------------------- #
# Imports and public-call fixture
# --------------------------------------------------------------------------- #
import math

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.redundancy import correlation_groups, feature_correlations


def correlations(frame, **kwargs):
    return feature_correlations(
        frame, feature_columns=frame.columns, sample_scope="observed rows", method="pearson", min_pairs=2, **kwargs
    )


# --------------------------------------------------------------------------- #
# Independent answers and estimands
# --------------------------------------------------------------------------- #


def test_signed_pearson_and_pairwise_counts():
    frame = pl.DataFrame({"a": [1.0, 2.0, 3.0, None, float("inf")], "b": [3.0, 2.0, 1.0, 99.0, 8.0]})
    result = correlations(frame)
    row = result.filter(pl.col("feature_left") != pl.col("feature_right")).row(0, named=True)
    assert row["correlation"] == pytest.approx(-1.0, abs=1e-12, rel=0)
    assert [row[key] for key in ["n_total", "n_valid", "n_missing_pair", "n_nonfinite_pair"]] == [5, 3, 1, 1]
    assert result["n_valid"].to_list() == [3, 3, 5]
    assert_frame_equal(correlations(frame.reverse()), result)


def test_spearman_average_ties_and_monotone_invariance():
    frame = pl.DataFrame({"a": [1.0, 1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0, 4.0]})

    def run(data):
        return feature_correlations(data, feature_columns=["a", "b"], sample_scope="s", method="spearman", min_pairs=4)

    # Midranks yield centered products 4.5 / sqrt(4.5*5).
    assert run(frame)["correlation"][1] == pytest.approx(3 / math.sqrt(10), abs=1e-12, rel=0)
    assert_frame_equal(run(frame), run(frame.with_columns(pl.col("a").exp(), pl.col("b") ** 3)))


def test_pearson_extremes_and_affine_invariance():
    frame = pl.DataFrame({"a": [-1e308, 0.0, 1e308], "b": [3.0, 2.0, 1.0]})
    assert correlations(frame)["correlation"][1] == pytest.approx(-1.0, abs=1e-12, rel=0)
    close = pl.DataFrame(
        {"a": [1.0, np.nextafter(1.0, 2.0), np.nextafter(np.nextafter(1.0, 2.0), 2.0)], "b": [1.0, 2.0, 3.0]}
    )
    assert correlations(close)["correlation"][1] == pytest.approx(1.0, abs=1e-12, rel=0)
    changed = frame.with_columns(pl.col("b") * 4 + 7)
    assert_frame_equal(correlations(frame), correlations(changed))


def test_constants_empty_and_exclusion_precedence():
    frame = pl.DataFrame({"a": [1.0, 1.0, None], "b": [2.0, 3.0, float("inf")]})
    result = correlations(frame)
    assert result["status"].to_list() == ["constant_both", "constant_left", "ok"]
    assert result["n_missing_pair"][1] == 1
    assert result["n_nonfinite_pair"][1] == 0
    empty = correlations(frame.head(0))
    assert empty["status"].to_list() == ["insufficient_pairs"] * 3
    assert empty["correlation"].null_count() == 3
    assert empty.schema["n_valid"] == pl.UInt64


def test_transitive_graph_is_explicit_and_retains_every_feature():
    # Unit vectors whose correlations are cos(0), cos(40deg), cos(80deg):
    # adjacent edges exceed .7; endpoints do not. Centered orthonormal vectors.
    x = np.array([-1.0, 0.0, 1.0]) / math.sqrt(2)
    y = np.array([1.0, -2.0, 1.0]) / math.sqrt(6)
    frame = pl.DataFrame(
        {
            "a": x,
            "b": math.cos(math.radians(40)) * x + math.sin(math.radians(40)) * y,
            "c": math.cos(math.radians(80)) * x + math.sin(math.radians(80)) * y,
            "d": -x,
        }
    )
    pairs = correlations(frame)
    grouped = correlation_groups(pairs, threshold=0.7, absolute=False)
    assert grouped["feature"].to_list() == ["a", "b", "c", "d"]
    assert grouped["group"].to_list() == ["a", "a", "a", "d"]
    assert correlation_groups(pairs, threshold=0.7, absolute=True)["group"].to_list() == ["a"] * 4
    assert_frame_equal(grouped, correlation_groups(pairs.reverse(), threshold=0.7, absolute=False))


# --------------------------------------------------------------------------- #
# Rejection contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method,min_pairs", [("kendall", 2), ("pearson", True), ("pearson", 1), ("pearson", 2**64)])
def test_invalid_controls(method, min_pairs):
    with pytest.raises(ValueError):
        feature_correlations(
            pl.DataFrame({"a": [1.0, 2.0]}), feature_columns=["a"], sample_scope="s", method=method, min_pairs=min_pairs
        )


def test_invalid_graph_and_feature_contracts():
    with pytest.raises(TypeError):
        correlations(pl.DataFrame({"a": [1, 2]}))
    pairs = correlations(pl.DataFrame({"a": [1.0, 2.0], "b": [2.0, 1.0]}))
    for threshold in [float("nan"), True, 1.01]:
        with pytest.raises(ValueError):
            correlation_groups(pairs, threshold=threshold, absolute=True)
    with pytest.raises(ValueError):
        correlation_groups(pairs.slice(1), threshold=0.5, absolute=True)
    with pytest.raises(ValueError):
        correlation_groups(pairs.with_columns(pl.lit(2.0).alias("correlation")), threshold=0.5, absolute=True)
