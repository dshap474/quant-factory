"""Build fold-local, sklearn-compatible tabular preprocessing.

Usage::

    transformer = build_preprocessor(config.preprocessing, config.feature_cols)
    transformer.fit(train_frame, train_target)
    train_matrix = transformer.transform(train_frame)
    eval_matrix = transformer.transform(eval_frame)

The returned :class:`~sklearn.pipeline.Pipeline` validates the feature schema
on every call, then learns only the configured imputation, scaling, clipping,
and selection state from ``fit`` data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_selection import SelectKBest, f_classif, f_regression
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MaxAbsScaler, MinMaxScaler, RobustScaler, StandardScaler

from .config import PreprocessingConfig

# --------------------------------------------------------------------------- #
# Schema and learned transformers
# --------------------------------------------------------------------------- #


class _SchemaGuard(BaseEstimator, TransformerMixin):
    """Validate and reorder DataFrame inputs at the sklearn boundary."""

    def __init__(
        self,
        feature_cols: Sequence[str],
        missing_policy: str = "error",
        extra_columns: str = "ignore",
    ) -> None:
        self.feature_cols = tuple(feature_cols)
        self.missing_policy = missing_policy
        self.extra_columns = extra_columns

    def fit(self, X: pd.DataFrame, y: Any = None) -> _SchemaGuard:
        del y
        selected = self._validate(X)
        self.feature_names_in_ = np.asarray(self.feature_cols, dtype=object)
        self.n_features_in_ = len(self.feature_cols)
        self.dtypes_in_ = tuple(selected.dtypes.astype(str))
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return self._validate(X)

    def get_feature_names_out(self, input_features: Sequence[str] | None = None) -> np.ndarray:
        del input_features
        return np.asarray(self.feature_cols, dtype=object)

    def _validate(self, X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("Preprocessing input must be a pandas.DataFrame")
        if not X.columns.is_unique:
            raise ValueError("Preprocessing input must not contain duplicate column names")
        missing = [column for column in self.feature_cols if column not in X.columns]
        if missing:
            raise ValueError(f"Missing required feature columns: {missing}")
        if self.extra_columns not in {"ignore", "error"}:
            raise ValueError("extra_columns must be 'ignore' or 'error'")
        if self.extra_columns == "error":
            extras = [column for column in X.columns if column not in self.feature_cols]
            if extras:
                raise ValueError(f"Unexpected feature columns: {extras}")

        selected = X.loc[:, list(self.feature_cols)].copy()
        bad_dtype = [
            column for column in self.feature_cols if not is_numeric_dtype(selected[column])
        ]
        if bad_dtype:
            raise TypeError(f"Configured features must be numeric: {bad_dtype}")

        if self.missing_policy == "error" and selected.isna().any().any():
            raise ValueError("Missing feature values are not allowed without an imputer")
        numeric = selected.select_dtypes(include=[np.number])
        if not numeric.empty and np.isinf(numeric.to_numpy(dtype=float, copy=False)).any():
            raise ValueError("Feature values must not be infinite")
        return selected


class _Clipper(BaseEstimator, TransformerMixin):
    """Apply fixed per-feature clipping without fitting on evaluation rows."""

    def __init__(
        self,
        lower: Any = None,
        upper: Any = None,
        feature_names: Sequence[str] | None = None,
    ) -> None:
        self.lower = lower
        self.upper = upper
        self.feature_names = tuple(feature_names) if feature_names is not None else None

    def fit(self, X: Any, y: Any = None) -> _Clipper:
        del y
        self.n_features_in_ = int(np.asarray(X).shape[1])
        self.feature_names_in_ = (
            np.asarray(self.feature_names, dtype=object)
            if self.feature_names is not None
            else _input_feature_names(X, self.n_features_in_)
        )
        self.lower_ = _bound_array(
            self.lower, self.feature_names_in_, self.n_features_in_, default=-np.inf
        )
        self.upper_ = _bound_array(
            self.upper, self.feature_names_in_, self.n_features_in_, default=np.inf
        )
        if np.any(self.lower_ > self.upper_):
            raise ValueError("Clip lower bounds must not exceed upper bounds")
        return self

    def transform(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Clipper received an unexpected feature shape")
        return np.clip(values, self.lower_, self.upper_)

    def get_feature_names_out(self, input_features: Sequence[str] | None = None) -> np.ndarray:
        return np.asarray(
            input_features if input_features is not None else self.feature_names_in_, dtype=object
        )


class _QuantileClipper(BaseEstimator, TransformerMixin):
    """Fit winsorization bounds on each fold's training matrix."""

    def __init__(self, lower_quantile: float = 0.01, upper_quantile: float = 0.99) -> None:
        self.lower_quantile = lower_quantile
        self.upper_quantile = upper_quantile

    def fit(self, X: Any, y: Any = None) -> _QuantileClipper:
        del y
        if not 0 <= self.lower_quantile < self.upper_quantile <= 1:
            raise ValueError("Winsorization quantiles must satisfy 0 <= lower < upper <= 1")
        values = np.asarray(X, dtype=float)
        if values.ndim != 2:
            raise ValueError("Winsorizer expects a two-dimensional matrix")
        self.n_features_in_ = values.shape[1]
        self.feature_names_in_ = _input_feature_names(X, self.n_features_in_)
        self.lower_ = np.nanquantile(values, self.lower_quantile, axis=0)
        self.upper_ = np.nanquantile(values, self.upper_quantile, axis=0)
        return self

    def transform(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Winsorizer received an unexpected feature shape")
        return np.clip(values, self.lower_, self.upper_)

    def get_feature_names_out(self, input_features: Sequence[str] | None = None) -> np.ndarray:
        return np.asarray(
            input_features if input_features is not None else self.feature_names_in_, dtype=object
        )


class _SafeSelectKBest(SelectKBest):
    """Select up to ``k`` features, treating oversized k as passthrough."""

    def fit(self, X: Any, y: Any) -> _SafeSelectKBest:
        if isinstance(self.k, Real) and not isinstance(self.k, bool):
            self.k = min(int(self.k), np.asarray(X).shape[1])
        return super().fit(X, y)


# --------------------------------------------------------------------------- #
# Configuration normalization
# --------------------------------------------------------------------------- #


def _input_feature_names(X: Any, count: int) -> np.ndarray:
    """Extract input names where available, otherwise use stable positions."""

    names = getattr(X, "columns", None)
    if names is not None and len(names) == count:
        return np.asarray(names, dtype=object)
    return np.asarray([f"x{i}" for i in range(count)], dtype=object)


def _bound_array(bound: Any, names: np.ndarray, count: int, *, default: float) -> np.ndarray:
    """Normalize scalar, sequence, or per-column mapping bounds."""

    if bound is None:
        return np.full(count, default, dtype=float)
    if isinstance(bound, Mapping):
        return np.asarray([bound.get(name, default) for name in names], dtype=float)
    if isinstance(bound, Real):
        return np.full(count, float(bound), dtype=float)
    values = np.asarray(bound, dtype=float)
    if values.shape != (count,):
        raise ValueError("Clip bounds must be scalars, mappings, or one value per feature")
    return values


def _make_imputer(config: PreprocessingConfig) -> Any | None:
    """Create a cloneable imputer from the canonical strategy."""

    setting = config.impute_strategy
    if setting is None:
        return None
    kwargs: dict[str, Any] = {"strategy": str(setting)}
    if setting == "constant":
        kwargs["fill_value"] = config.impute_fill_value
    return SimpleImputer(**kwargs)


def _make_scaler(config: PreprocessingConfig) -> Any | None:
    """Create the configured numeric scaler."""

    setting = config.scale
    if setting is None:
        return None
    scalers = {
        "standard": StandardScaler,
        "minmax": MinMaxScaler,
        "robust": RobustScaler,
        "maxabs": MaxAbsScaler,
    }
    return scalers[setting]()


def _clip_steps(
    config: PreprocessingConfig,
    feature_cols: Sequence[str],
) -> list[tuple[str, Any]]:
    """Build fixed or learned clipping steps from canonical bounds."""

    winsorize = config.winsorize

    if winsorize is not None:
        lower, upper = winsorize
        return [("clip", _QuantileClipper(float(lower), float(upper)))]

    if config.clip_min is not None or config.clip_max is not None:
        return [
            (
                "clip",
                _Clipper(
                    config.clip_min,
                    config.clip_max,
                    feature_names=feature_cols,
                ),
            )
        ]
    return []


def _make_selector(config: PreprocessingConfig, task: str) -> Any | None:
    """Create an optional fold-local feature selector."""

    k = config.max_features
    if k is None:
        return None
    if int(k) < 1:
        raise ValueError("max_features must be at least one")
    score_func = f_classif if task == "binary_classification" else f_regression
    return _SafeSelectKBest(score_func=score_func, k=int(k))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def build_preprocessor(
    config: PreprocessingConfig,
    feature_cols: Sequence[str],
    *,
    task: str = "regression",
) -> Pipeline:
    """Build an unfitted, cloneable sklearn preprocessing pipeline.

    The first step always enforces the ordered DataFrame feature schema.  All
    later steps are newly constructed for each call, so callers can safely
    clone and fit one instance per chronological fold.
    """

    if not isinstance(config, PreprocessingConfig):
        raise TypeError("config must be a PreprocessingConfig")
    features = tuple(feature_cols)
    if not features or len(set(features)) != len(features):
        raise ValueError("feature_cols must be a non-empty sequence of unique names")

    missing_policy = str(config.missing_policy).lower()
    extra_columns = str(config.extra_columns).lower()
    imputer = _make_imputer(config)
    scaler = _make_scaler(config)
    clip_steps = _clip_steps(config, features)
    if task not in {"regression", "binary_classification"}:
        raise ValueError(f"unsupported task: {task!r}")
    selector = _make_selector(config, task)

    schema_missing_policy = "allow" if imputer is not None else missing_policy
    steps: list[tuple[str, Any]] = [
        (
            "schema",
            _SchemaGuard(
                features,
                missing_policy=schema_missing_policy,
                extra_columns=extra_columns,
            ),
        )
    ]
    if imputer is not None:
        steps.append(("imputer", imputer))
    steps.extend(clip_steps)
    if scaler is not None:
        steps.append(("scaler", scaler))
    if selector is not None:
        steps.append(("feature_selection", selector))
    return Pipeline(steps)
