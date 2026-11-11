"""Fit explicit PCA bases and diagnose eigenvalue/importance rank agreement.

Usage: ``basis = fit_pca(train, feature_columns=["x", "y"],
fit_sample_scope="fold 1 train", purpose="training", n_components=None)``;
``scores = transform_pca(test, basis)``. No estimator training or I/O occurs.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and immutable fitted values
# --------------------------------------------------------------------------- #
from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum
from typing import Literal

import numpy as np
import polars as pl
from scipy.stats import weightedtau

from .contracts import validate_feature_frame


@dataclass(frozen=True)
class PCABasis:
    """Fitted sample-standardized PCA, stored as immutable numeric tuples.

    ``means`` are rounded presentation values. Transformation uses the more
    accurate two-part center ``origins + center_offsets``, preserving variation
    near large offsets. Components have shape (features, retained components).
    Eigenvalues are sample covariance eigenvalues, not Gram eigenvalues.
    Purpose and fit_sample_scope are caller declarations, not leakage audits.
    """

    feature_columns: tuple[str, ...]
    means: tuple[float, ...]
    origins: tuple[float, ...]
    center_offsets: tuple[float, ...]
    scales: tuple[float, ...]
    components: tuple[tuple[float, ...], ...]
    eigenvalues: tuple[float, ...]
    explained_variance_ratio: tuple[float | None, ...]
    constant_features: tuple[str, ...]
    numerical_rank: int
    n_fit: int
    fit_sample_scope: str
    purpose: Literal["descriptive", "training"]
    status: str


# --------------------------------------------------------------------------- #
# Stable standardization
# --------------------------------------------------------------------------- #


def _standardize(values: np.ndarray, origins: np.ndarray, offsets: np.ndarray, scales: np.ndarray) -> np.ndarray:
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        centered = (values - origins - offsets) / scales
        fallback = values / scales - origins / scales - offsets / scales
    result = np.where(np.isfinite(centered), centered, fallback)
    if not np.isfinite(result).all():
        raise ArithmeticError("standardized values are outside the finite Float64 domain")
    return result


def _finite_matrix(frame: pl.DataFrame, feature_columns: Sequence[str]) -> np.ndarray:
    validate_feature_frame(frame, feature_columns=feature_columns)
    values = frame.select(feature_columns).to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("PCA requires complete finite feature rows; select the fit sample explicitly")
    return values


# --------------------------------------------------------------------------- #
# Public PCA fit and transform
# --------------------------------------------------------------------------- #


def fit_pca(
    frame: pl.DataFrame,
    *,
    feature_columns: Sequence[str],
    fit_sample_scope: str,
    purpose: Literal["descriptive", "training"],
    n_components: int | None,
) -> PCABasis:
    """Fit means, sample scales (ddof=1), and an SVD basis on supplied rows.

    None retains min(n_rows, n_features) components, including zero directions.
    Constants use scale 1 and score zero in the fit sample, and remain named.
    No explained-variance threshold or feature selection is applied. Predictive
    callers must fit within each ML training partition and reuse that basis.
    """
    values = _finite_matrix(frame, feature_columns)
    if (
        not isinstance(fit_sample_scope, str)
        or not fit_sample_scope.strip()
        or fit_sample_scope != fit_sample_scope.strip()
    ):
        raise ValueError("fit_sample_scope must be a nonempty trimmed string")
    if purpose not in ("descriptive", "training"):
        raise ValueError("purpose must be descriptive or training")
    n, p = values.shape
    if n < 2:
        raise ValueError("PCA fitting requires at least two rows")
    maximum = min(n, p)
    if n_components is not None and (
        isinstance(n_components, bool) or not isinstance(n_components, int) or not 1 <= n_components <= maximum
    ):
        raise ValueError("n_components must be None or an integer in [1,min(n_rows,n_features)]")
    count = maximum if n_components is None else n_components
    origins, offsets, scales, constants = [], [], [], []
    for index, name in enumerate(feature_columns):
        column = values[:, index]
        origin = float(column[0])
        with np.errstate(over="ignore"):
            delta = column - origin
        if not np.isfinite(delta).all():
            origin, delta = 0.0, column.copy()
        offset = fsum(float(value) / n for value in delta)
        if np.all(column == column[0]):
            scale = 1.0
            constants.append(name)
        else:
            peak = float(np.max(np.abs(delta)))
            normalized = delta / peak - offset / peak
            scale = float(np.linalg.norm(normalized) / np.sqrt(n - 1) * peak)
            if not np.isfinite(scale) or scale < np.finfo(float).tiny:
                raise ArithmeticError("sample standard deviation is outside the normal positive finite Float64 domain")
        origins.append(origin)
        offsets.append(offset)
        scales.append(scale)
    z = _standardize(values, np.array(origins), np.array(offsets), np.array(scales))
    _, singular, vt = np.linalg.svd(z, full_matrices=False)
    # A sign convention improves repeatability; repeated eigenspaces are still
    # mathematically non-unique and must be compared through subspace projectors.
    components = vt[:count].T.copy()
    for column in range(count):
        pivot = int(np.argmax(np.abs(components[:, column])))
        if components[pivot, column] < 0:
            components[:, column] *= -1
    eigenvalues = singular**2 / (n - 1)
    total = float(eigenvalues.sum())
    rank = int(np.sum(singular > np.finfo(float).eps * max(n, p) * singular[0]))
    return PCABasis(
        feature_columns=tuple(feature_columns),
        means=tuple(fsum((origin, offset)) for origin, offset in zip(origins, offsets, strict=True)),
        origins=tuple(origins),
        center_offsets=tuple(offsets),
        scales=tuple(scales),
        components=tuple(tuple(float(value) for value in row) for row in components),
        eigenvalues=tuple(float(value) for value in eigenvalues[:count]),
        explained_variance_ratio=tuple(float(value / total) if total > 0 else None for value in eigenvalues[:count]),
        constant_features=tuple(constants),
        numerical_rank=rank,
        n_fit=n,
        fit_sample_scope=fit_sample_scope,
        purpose=purpose,
        status="no_variation" if total == 0 else "rank_deficient" if rank < p else "ok",
    )


def transform_pca(frame: pl.DataFrame, basis: PCABasis) -> pl.DataFrame:
    """Align columns by saved feature names and apply the fixed fitted basis.

    Extra columns are ignored, missing columns and nonfinite values rejected.
    New values in formerly constant features are centered with their fitted
    scale 1; they are not silently reset to zero. No refitting occurs.
    """
    if not isinstance(basis, PCABasis):
        raise TypeError("basis must be PCABasis")
    values = _finite_matrix(frame, feature_columns=basis.feature_columns)
    p, k = len(basis.feature_columns), len(basis.eigenvalues)
    arrays = [np.asarray(item, dtype=float) for item in (basis.origins, basis.center_offsets, basis.scales)]
    components = np.asarray(basis.components, dtype=float)
    if any(array.shape != (p,) or not np.isfinite(array).all() for array in arrays):
        raise ValueError("basis has malformed center or scale arrays")
    if np.any(arrays[2] <= 0) or components.shape != (p, k) or k < 1 or not np.isfinite(components).all():
        raise ValueError("basis has malformed scales or components")
    transformed = _standardize(values, *arrays) @ components
    if not np.isfinite(transformed).all():
        raise ArithmeticError("PCA scores are outside the finite Float64 domain")
    return pl.DataFrame(transformed, schema=[f"PC_{index + 1}" for index in range(k)], orient="row")


# --------------------------------------------------------------------------- #
# Eigenvalue and supplied importance agreement
# --------------------------------------------------------------------------- #


def eigenvalue_importance_agreement(observations: pl.DataFrame, *, sample_scope: str) -> pl.DataFrame:
    """Return additive hyperbolic weighted Kendall agreement, without inference.

    Required columns are component:String (unique), eigenvalue:Float64, and
    importance:Float64. Larger scores rank higher; signed importances are valid.
    SciPy rank=True averages decreasing lexicographic (x,y) and (y,x) rankings.
    Score ties enter the weighted Kendall tie normalization. Missing/nonfinite
    pairs are excluded explicitly. Negative finite eigenvalues are rejected.
    """
    validate_feature_frame(observations, feature_columns=["eigenvalue", "importance"])
    if "component" not in observations.schema or observations.schema["component"] != pl.String:
        raise TypeError("component must have String dtype")
    ids = observations["component"].to_list()
    if any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in ids) or len(
        set(ids)
    ) != len(ids):
        raise ValueError("component identifiers must be unique nonempty trimmed strings")
    if not isinstance(sample_scope, str) or not sample_scope.strip() or sample_scope != sample_scope.strip():
        raise ValueError("sample_scope must be a nonempty trimmed string")
    if observations.filter(pl.col("eigenvalue").is_finite() & (pl.col("eigenvalue") < 0)).height:
        raise ValueError("finite eigenvalues must be nonnegative")
    missing = observations["eigenvalue"].is_null() | observations["importance"].is_null()
    finite = (observations["eigenvalue"].is_finite() & observations["importance"].is_finite()).fill_null(False)
    valid = observations.filter(~missing & finite).sort("component")
    value, status = None, "insufficient_pairs"
    if valid.height >= 2:
        x, y = valid["eigenvalue"].to_numpy(), valid["importance"].to_numpy()
        cx, cy = bool(np.all(x == x[0])), bool(np.all(y == y[0]))
        if cx or cy:
            status = "constant_both" if cx and cy else "constant_eigenvalue" if cx else "constant_importance"
        else:
            value = float(weightedtau(x, y, rank=True, additive=True).statistic)
            if not np.isfinite(value):
                raise ArithmeticError("nonfinite weighted rank agreement")
            status = "ok"
    return pl.DataFrame(
        [
            {
                "sample_scope": sample_scope,
                "method": "weighted_kendall_hyperbolic_symmetric",
                "agreement": value,
                "status": status,
                "n_total": observations.height,
                "n_valid": valid.height,
                "n_missing_pair": int(missing.sum()),
                "n_nonfinite_pair": int((~missing & ~finite).sum()),
            }
        ],
        schema={
            "sample_scope": pl.String,
            "method": pl.String,
            "agreement": pl.Float64,
            "status": pl.String,
            "n_total": pl.UInt64,
            "n_valid": pl.UInt64,
            "n_missing_pair": pl.UInt64,
            "n_nonfinite_pair": pl.UInt64,
        },
    )


__all__ = ["PCABasis", "fit_pca", "transform_pca", "eigenvalue_importance_agreement"]
