"""Verify MDI against hand-derived tree statistics and attribution invariants.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_importance_mdi.py``.
"""

# --------------------------------------------------------------------------- #
# Imports and exact tree fixtures
# --------------------------------------------------------------------------- #
import math

import polars as pl
import pytest

from signal_analysis.importance.mdi import mean_decrease_impurity


def trees() -> pl.DataFrame:
    return pl.DataFrame({"tree_id": ["a", "b", "c", "d"], "x": [1.0, 0.6, 0.0, 0.0], "y": [0.0, 0.4, 1.0, 1.0]})


# --------------------------------------------------------------------------- #
# Public operation verification
# --------------------------------------------------------------------------- #


def test_known_answers_distinguish_zero_semantics_and_total_tree_denominator():
    conventional = mean_decrease_impurity(trees(), feature_columns=["x", "y"], normalization="conventional")
    book = mean_decrease_impurity(trees(), feature_columns=["x", "y"], normalization="afml_zero_excluded")
    assert conventional.summary["importance"].to_list() == pytest.approx([0.4, 0.6], abs=1e-12)
    assert book.summary["importance"].to_list() == pytest.approx([0.5, 0.5], abs=1e-12)
    # Nonzero x: (1,.6), mean=.8, sample variance=.08. Four total trees.
    # Nonzero y: (.4,1,1), mean=.8, sample variance=.12. Normalize by 1.6.
    assert book.summary["scaled_tree_dispersion"].to_list() == pytest.approx(
        [math.sqrt(0.08) / 3.2, math.sqrt(0.12) / 3.2], abs=1e-12
    )
    assert book.summary["n_included"].to_list() == [2, 3]
    assert book.raw.height == 8
    assert book.raw.filter(pl.col("tree_importance") == 0)["included"].to_list() == [False] * 3


@pytest.mark.parametrize("normalization", ["conventional", "afml_zero_excluded"])
def test_tree_and_feature_permutation_invariance(normalization):
    left = mean_decrease_impurity(trees(), feature_columns=["x", "y"], normalization=normalization)
    right = mean_decrease_impurity(trees().reverse(), feature_columns=["y", "x"], normalization=normalization)
    assert right.summary.sort("feature").equals(left.summary.sort("feature"))
    assert left.summary["importance"].sum() == pytest.approx(1.0, abs=1e-12)


def test_no_split_and_never_selected_features_remain_explicit():
    frame = pl.DataFrame({"tree_id": ["a"], "x": [0.0], "y": [0.0]})
    conventional = mean_decrease_impurity(frame, feature_columns=["x", "y"], normalization="conventional")
    assert conventional.summary["importance"].null_count() == 2
    assert conventional.summary["status"].to_list() == ["zero_total_importance"] * 2
    book = mean_decrease_impurity(frame, feature_columns=["x", "y"], normalization="afml_zero_excluded")
    assert book.summary["status"].to_list() == ["no_nonzero_trees"] * 2
    frame = frame.with_columns(pl.lit(1.0).alias("x"))
    book = mean_decrease_impurity(frame, feature_columns=["x", "y"], normalization="afml_zero_excluded")
    assert book.summary["importance"].to_list() == [1.0, None]
    assert book.summary["scaled_tree_dispersion"].null_count() == 2


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), 2.0])
def test_invalid_tree_statistics_rejected(bad):
    frame = pl.DataFrame({"tree_id": ["a"], "x": [bad]})
    with pytest.raises(ValueError):
        mean_decrease_impurity(frame, feature_columns=["x"], normalization="conventional")


def test_duplicate_trees_and_empty_input_rejected():
    with pytest.raises(ValueError):
        mean_decrease_impurity(
            trees().with_columns(pl.lit("same").alias("tree_id")),
            feature_columns=["x", "y"],
            normalization="conventional",
        )
    with pytest.raises(ValueError):
        mean_decrease_impurity(trees().head(0), feature_columns=["x", "y"], normalization="conventional")


def test_small_tree_spread_is_centered_before_scaling():
    epsilon = 2**-53
    frame = pl.DataFrame({"tree_id": ["a", "b"], "x": [0.5, 0.5 + epsilon], "y": [0.5, 0.5 - epsilon]})
    result = mean_decrease_impurity(frame, feature_columns=["x", "y"], normalization="conventional")
    # Two values separated by epsilon have sample SD epsilon/sqrt(2).
    assert result.summary["tree_sample_std"].to_list() == pytest.approx([epsilon / math.sqrt(2)] * 2, rel=1e-14, abs=0)
