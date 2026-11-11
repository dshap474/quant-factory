"""Independent PCA subspace/reconstruction and weighted-rank agreement oracles.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_orthogonalization.py``.
Float64 tolerance 1e-12 covers small well-conditioned LAPACK rounding; tests
compare projectors/reconstructions instead of arbitrary eigenvector signs.
"""

# --------------------------------------------------------------------------- #
# Imports and direct public operations
# --------------------------------------------------------------------------- #
import math
from dataclasses import FrozenInstanceError
from fractions import Fraction
from itertools import combinations

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.orthogonalization import eigenvalue_importance_agreement, fit_pca, transform_pca


def fit(frame, count=None):
    return fit_pca(
        frame,
        feature_columns=frame.columns,
        fit_sample_scope="known train rows",
        purpose="training",
        n_components=count,
    )


def agreement(x, y):
    return eigenvalue_importance_agreement(
        pl.DataFrame(
            {"component": [f"p{i}" for i in range(len(x))], "eigenvalue": x, "importance": y},
            schema={"component": pl.String, "eigenvalue": pl.Float64, "importance": pl.Float64},
        ),
        sample_scope="component fit",
    ).row(0, named=True)


# --------------------------------------------------------------------------- #
# PCA independently derived fixtures and invariants
# --------------------------------------------------------------------------- #


def test_two_identical_features_have_hand_derived_rank_one_projector():
    frame = pl.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    basis = fit(frame)
    assert basis.means == (2.0, 20.0)
    assert basis.scales == pytest.approx((1.0, 10.0), abs=1e-12, rel=0)
    assert basis.eigenvalues == pytest.approx((2.0, 0.0), abs=1e-12, rel=0)
    assert basis.explained_variance_ratio == pytest.approx((1.0, 0.0), abs=1e-12, rel=0)
    assert basis.numerical_rank == 1
    assert basis.status == "rank_deficient"
    vector = np.asarray(basis.components)[:, 0]
    np.testing.assert_allclose(np.outer(vector, vector), np.full((2, 2), 0.5), atol=1e-12, rtol=0)
    scores = transform_pca(frame, basis).to_numpy()
    np.testing.assert_allclose(
        scores @ np.asarray(basis.components).T, [[-1.0, -1.0], [0.0, 0.0], [1.0, 1.0]], atol=1e-12, rtol=0
    )
    np.testing.assert_allclose(scores.T @ scores / 2, np.diag(basis.eigenvalues), atol=1e-12, rtol=0)


def test_repeated_eigenvalues_compare_complete_subspace_and_reconstruction():
    frame = pl.DataFrame({"x": [-1.0, -1.0, 1.0, 1.0], "y": [-1.0, 1.0, -1.0, 1.0]})
    basis = fit(frame)
    assert basis.eigenvalues == pytest.approx([1.0, 1.0], abs=1e-12, rel=0)
    vectors = np.asarray(basis.components)
    np.testing.assert_allclose(vectors @ vectors.T, np.eye(2), atol=1e-12, rtol=0)
    scores = transform_pca(frame, basis).to_numpy()
    np.testing.assert_allclose(scores @ vectors.T, frame.to_numpy() * math.sqrt(3) / 2, atol=1e-12, rtol=0)
    assert fit(frame) == basis
    permuted = fit(frame.reverse())
    np.testing.assert_allclose(
        np.asarray(permuted.components) @ np.asarray(permuted.components).T, vectors @ vectors.T, atol=1e-12, rtol=0
    )


def test_constants_rank_deficiency_and_more_features_than_rows():
    frame = pl.DataFrame({"a": [1.0, 2.0], "b": [2.0, 4.0], "constant": [3.0, 3.0]})
    basis = fit(frame)
    assert basis.numerical_rank == 1
    assert basis.constant_features == ("constant",)
    assert len(basis.eigenvalues) == 2
    reconstructed = transform_pca(frame, basis).to_numpy() @ np.asarray(basis.components).T
    np.testing.assert_allclose(
        reconstructed,
        [[-1 / math.sqrt(2), -1 / math.sqrt(2), 0.0], [1 / math.sqrt(2), 1 / math.sqrt(2), 0.0]],
        atol=1e-12,
        rtol=0,
    )


def test_all_constant_has_no_explained_variation():
    frame = pl.DataFrame({"a": [3.0, 3.0, 3.0], "b": [-2.0, -2.0, -2.0]})
    basis = fit(frame)
    assert basis.status == "no_variation"
    assert basis.numerical_rank == 0
    assert basis.eigenvalues == (0.0, 0.0)
    assert basis.explained_variance_ratio == (None, None)
    assert basis.constant_features == ("a", "b")
    np.testing.assert_array_equal(transform_pca(frame, basis).to_numpy(), np.zeros((3, 2)))


def test_transform_uses_frozen_fit_and_named_alignment():
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    basis = fit(train, 1)
    test = pl.DataFrame({"x": [4.0, 5.0], "y": [40.0, 50.0]})
    transformed = transform_pca(test, basis)
    assert transformed["PC_1"].to_list() == pytest.approx([2 * math.sqrt(2), 3 * math.sqrt(2)], abs=1e-12, rel=0)
    assert_frame_equal(
        transformed, transform_pca(test.select("y", "x").with_columns(pl.lit("extra").alias("tag")), basis)
    )
    assert_frame_equal(transformed.head(1), transform_pca(test.head(1), basis))
    assert transform_pca(test.head(0), basis).schema == {"PC_1": pl.Float64}
    with pytest.raises(FrozenInstanceError):
        basis.n_fit = 99


def test_scale_extremes_and_adjacent_large_floats():
    for scale in [1e-300, 1.0, 1e300]:
        basis = fit(pl.DataFrame({"x": [-scale, 0.0, scale]}))
        assert basis.eigenvalues == pytest.approx([1.0], abs=1e-12, rel=0)
    x = 1e300
    frame = pl.DataFrame({"x": [x, np.nextafter(x, np.inf)]})
    basis = fit(frame)
    # Mean lies halfway between adjacent floats, so two-part centering matters.
    assert basis.eigenvalues == pytest.approx([1.0], abs=1e-12, rel=0)
    np.testing.assert_allclose(
        np.abs(transform_pca(frame, basis).to_numpy()), [[1 / math.sqrt(2)], [1 / math.sqrt(2)]], atol=1e-12, rtol=0
    )


# --------------------------------------------------------------------------- #
# Independent pair-enumeration oracle, distinct from SciPy mergesort
# --------------------------------------------------------------------------- #


def pair_tau(x, y):
    results = []
    for first, second in [(x, y), (y, x)]:
        order = sorted(range(len(x)), key=lambda i: (first[i], second[i]), reverse=True)
        weights = {index: Fraction(1, rank + 1) for rank, index in enumerate(order)}
        numerator = denominator_x = denominator_y = Fraction(0)
        for i, j in combinations(range(len(x)), 2):
            weight = weights[i] + weights[j]
            dx = (x[i] > x[j]) - (x[i] < x[j])
            dy = (y[i] > y[j]) - (y[i] < y[j])
            numerator += weight * dx * dy
            denominator_x += weight * abs(dx)
            denominator_y += weight * abs(dy)
        results.append(float(numerator) / math.sqrt(float(denominator_x * denominator_y)))
    return sum(results) / 2


def test_chapter_eight_weighted_rank_hand_answer():
    # Only bottom two disagree: discordant weight 1/3+1/4=7/12;
    # total exchange weight 3*(1+1/2+1/3+1/4)=25/4 -> 1-2*7/75.
    row = agreement([1.0, 0.5, 0.25, 1 / 3], [0.55, 0.33, 0.07, 0.05])
    assert row["agreement"] == pytest.approx(61 / 75, abs=1e-12, rel=0)
    assert row["method"] == "weighted_kendall_hyperbolic_symmetric"
    assert "pvalue" not in row


@pytest.mark.parametrize(
    "x,y",
    [
        ([4.0, 4.0, 2.0, 1.0], [3.0, 1.0, 1.0, 0.0]),
        ([4.0, 3.0, 2.0, 1.0], [1.0, 2.0, 3.0, 4.0]),
        ([1.0, 2.0, 2.0, 4.0], [-3.0, -1.0, -1.0, 9.0]),
    ],
)
def test_tie_aware_tau_matches_exact_pair_oracle(x, y):
    expected = pair_tau(x, y)
    assert agreement(x, y)["agreement"] == pytest.approx(expected, abs=1e-12, rel=0)
    assert agreement(list(reversed(x)), list(reversed(y)))["agreement"] == pytest.approx(expected, abs=1e-12, rel=0)


def test_rank_coverage_and_undefined_statuses():
    row = agreement([1.0, 2.0, None, float("nan")], [4.0, 3.0, float("inf"), 1.0])
    assert [row[key] for key in ["n_total", "n_valid", "n_missing_pair", "n_nonfinite_pair"]] == [4, 2, 1, 1]
    assert row["agreement"] == pytest.approx(-1.0, abs=1e-12, rel=0)
    assert agreement([1.0, 1.0], [1.0, 2.0])["status"] == "constant_eigenvalue"
    assert agreement([1.0, 2.0], [1.0, 1.0])["status"] == "constant_importance"
    assert agreement([1.0, 1.0], [1.0, 1.0])["status"] == "constant_both"
    assert agreement([], [])["status"] == "insufficient_pairs"
    with pytest.raises(ValueError):
        agreement([-1.0, 2.0], [1.0, 2.0])


@pytest.mark.parametrize("values", [[1.0], [], [1.0, None], [1.0, float("nan")], [1.0, float("inf")]])
def test_pca_invalid_rows(values):
    with pytest.raises(ValueError):
        fit(pl.DataFrame({"x": values}, schema={"x": pl.Float64}))


@pytest.mark.parametrize("count", [0, True, 3, 1.5])
def test_pca_invalid_component_count(count):
    with pytest.raises(ValueError):
        fit(pl.DataFrame({"x": [1.0, 2.0], "y": [2.0, 3.0]}), count)


def test_subnormal_fit_scale_is_explicitly_unsupported():
    # Half of the smallest subnormal cannot represent the centered mean/scale.
    # A finite-looking eigenvalue alone would miss a nonzero score mean here.
    with pytest.raises(ArithmeticError, match="normal positive"):
        fit(pl.DataFrame({"x": [0.0, float.fromhex("0x0.0000000000001p-1022")]}))


def test_large_unbalanced_fit_is_centered_with_sample_variance_one():
    frame = pl.DataFrame({"x": [0.0] * 7 + [1e308] * 3})
    basis = fit(frame)
    scores = transform_pca(frame, basis).to_numpy()
    assert basis.eigenvalues == pytest.approx([1.0], abs=1e-12, rel=0)
    assert scores.mean() == pytest.approx(0.0, abs=1e-12, rel=0)
    # Hand mixture scale: sqrt(10/9 * .3*.7)*1e308 = sqrt(7/30)*1e308.
    assert basis.scales[0] == pytest.approx(math.sqrt(7 / 30) * 1e308, abs=0, rel=1e-14)


def test_invalid_transform_and_scope_contracts():
    frame = pl.DataFrame({"x": [1.0, 2.0]})
    basis = fit(frame)
    with pytest.raises(TypeError):
        transform_pca(frame.rename({"x": "other"}), basis)
    with pytest.raises(ValueError):
        transform_pca(frame.with_columns(pl.lit(float("inf")).alias("x")), basis)
    for scope, purpose in [("", "training"), ("s", "OOS")]:
        with pytest.raises(ValueError):
            fit_pca(frame, feature_columns=["x"], fit_sample_scope=scope, purpose=purpose, n_components=None)


def test_mixed_multivariate_fit_covariance_residual_and_affine_invariance():
    # Independent covariance/eigh formulation checks the production SVD path.
    # The smaller hand fixtures remain the known-answer anchors.
    rng = np.random.default_rng(82)
    x = rng.normal(size=(31, 4))
    x[:, 2] += 2 * x[:, 0] - x[:, 1]
    x[:, 3] += x[:, 1] / 2
    frame = pl.DataFrame(x, schema=["a", "b", "c", "d"], orient="row")
    basis = fit(frame)
    covariance = np.cov(x, rowvar=False, ddof=1)
    deviations = np.sqrt(np.diag(covariance))
    correlation = covariance / np.outer(deviations, deviations)
    reference_eigenvalues, _ = np.linalg.eigh(correlation)
    assert basis.eigenvalues == pytest.approx(reference_eigenvalues[::-1], abs=1e-12, rel=0)
    w = np.asarray(basis.components)
    np.testing.assert_allclose(correlation @ w, w @ np.diag(basis.eigenvalues), atol=1e-12, rtol=0)
    scores = transform_pca(frame, basis).to_numpy()
    np.testing.assert_allclose(scores.mean(axis=0), np.zeros(4), atol=1e-12, rtol=0)
    np.testing.assert_allclose(
        (scores @ w.T) * np.asarray(basis.scales) + np.asarray(basis.means), x, atol=1e-12, rtol=0
    )
    rescaled = pl.DataFrame(
        x * np.array([2.0, 3.0, 4.0, 5.0]) + np.array([6.0, 7.0, 8.0, 9.0]), schema=frame.columns, orient="row"
    )
    changed = fit(rescaled)
    assert changed.eigenvalues == pytest.approx(basis.eigenvalues, abs=1e-12, rel=0)
    np.testing.assert_allclose(transform_pca(rescaled, changed).to_numpy(), scores, atol=1e-12, rtol=0)
