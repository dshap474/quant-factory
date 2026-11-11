"""Leakage-safe ensemble combiners for row-aligned out-of-sample predictions.

The module deliberately operates on predictions, rather than fitting base models.  It
supports fixed/equal weighted averages, simplex-constrained weight learning, and a
sklearn-compatible stacking combiner.  Learned combiners are evaluated with expanding,
chronological meta-folds; rows used to fit a meta-combiner are never used for its reported
prediction.

Usage:
    >>> from ml_engine.training.ensemble import fit_ensemble
    >>> result = fit_ensemble(config, {"a": [0., 1.], "b": [1., 0.]}, [0., 1.])
    >>> result.predict({"a": [0.2], "b": [0.8]})
    array([0.5])
"""

from __future__ import annotations

from collections.abc import Mapping

# --------------------------------------------------------------------------- #
# Imports and public types
# --------------------------------------------------------------------------- #
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import Ridge

from .config import EnsembleConfig


class EnsembleError(ValueError):
    """Raised when an ensemble cannot be constructed without leakage or ambiguity."""


@dataclass
class AlignedPredictions:
    """Wide, row-aligned prediction values and their optional metadata."""

    values: np.ndarray
    names: tuple[str, ...]
    row_ids: np.ndarray
    timestamps: np.ndarray
    target: np.ndarray | None


def _vector(values: Any, *, label: str) -> np.ndarray:
    """Return one numeric vector or fail with an ensemble-specific error."""

    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise EnsembleError(f"{label} must be numeric") from exc
    if array.ndim != 1:
        raise EnsembleError(f"{label} must be one-dimensional")
    return array


def _time_vector(values: Any, length: int) -> np.ndarray:
    """Return chronological values with a deterministic positional default."""

    if values is None:
        return np.arange(length, dtype=np.int64)
    if len(values) != length:
        raise EnsembleError("timestamps and predictions must have the same length")
    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    if parsed.isna().any():
        raise EnsembleError("timestamps must be valid datetime values")
    return parsed.to_numpy()


def _normalize_predictions(
    predictions: Any,
    *,
    allow_missing: bool = False,
) -> AlignedPredictions:
    """Pivot the package's normalized long OOS table for ensemble fitting."""

    if not isinstance(predictions, pd.DataFrame) or not {
        "candidate",
        "prediction",
    }.issubset(predictions.columns):
        raise EnsembleError("ensemble fitting requires a long OOS prediction table")
    frame = predictions.copy()
    if frame["candidate"].isna().any():
        raise EnsembleError("long predictions require candidate values")
    frame["candidate"] = frame["candidate"].astype(str)
    key = "row_id" if "row_id" in frame.columns else "__ensemble_row"
    if key == "__ensemble_row":
        frame[key] = frame.groupby("candidate", sort=False).cumcount()
    if frame.duplicated([key, "candidate"]).any():
        raise EnsembleError("each row_id/candidate pair must have one prediction")

    names = tuple(dict.fromkeys(frame["candidate"]))
    wide = frame.pivot(index=key, columns="candidate", values="prediction").reindex(
        columns=list(names)
    )
    if not allow_missing and wide.isna().any().any():
        raise EnsembleError("base predictions are not aligned across candidates")
    values = wide.to_numpy(dtype=float)

    inferred_row_ids = wide.index.to_numpy()
    inferred_timestamps = None
    inferred_target = None
    for column in ("timestamp", "target"):
        if column not in frame:
            continue
        if frame.groupby(key, sort=False)[column].nunique(dropna=False).gt(1).any():
            raise EnsembleError(f"aligned candidates must share one {column} per row_id")
        aligned = frame.drop_duplicates(key).set_index(key).reindex(wide.index)[column]
        if column == "timestamp":
            inferred_timestamps = aligned
        else:
            inferred_target = aligned

    length = len(wide)
    if len(inferred_row_ids) != length:
        raise EnsembleError("row_ids and predictions must have the same length")
    row_array = np.asarray(inferred_row_ids)
    if pd.isna(row_array).any() or pd.Index(row_array).duplicated().any():
        raise EnsembleError("row_ids must be non-null and unique")
    target_array = None if inferred_target is None else _vector(inferred_target, label="targets")
    if target_array is not None and len(target_array) != length:
        raise EnsembleError("targets and predictions must have the same length")
    if not allow_missing and not np.isfinite(values).all():
        raise EnsembleError("base predictions must be finite")
    return AlignedPredictions(
        values,
        names,
        row_array,
        _time_vector(inferred_timestamps, length),
        target_array,
    )


def _align_for_predict(
    predictions: Any,
    names: tuple[str, ...],
    *,
    allow_missing: bool = False,
) -> np.ndarray:
    """Return fitted model columns in their persisted order."""

    if isinstance(predictions, pd.DataFrame):
        missing = [name for name in names if name not in predictions]
        extras = [name for name in predictions if name not in names]
        if missing or extras:
            raise EnsembleError("prediction candidate names do not match the fitted ensemble")
        values = predictions.loc[:, list(names)].to_numpy(dtype=float)
    else:
        values = np.asarray(predictions, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(names):
            raise EnsembleError("prediction matrix does not match the fitted ensemble")
    if not allow_missing and not np.isfinite(values).all():
        raise EnsembleError("base predictions must be finite")
    return values


@dataclass(frozen=True)
class MetaFold:
    """Chronological train/evaluation row positions used for meta-cross-fitting."""

    fold: int
    train_indices: tuple[int, ...]
    evaluation_indices: tuple[int, ...]


@dataclass
class EnsembleResult:
    """Fitted ensemble and its strictly out-of-sample evaluation evidence."""

    kind: str
    model_names: tuple[str, ...]
    combiner: Any = None
    weights: np.ndarray | None = None
    # Full row-aligned predictions; learned modes contain NaN for meta-train-only rows.
    oos_predictions: np.ndarray | None = None
    meta_oos_predictions: np.ndarray | None = None
    meta_folds: tuple[MetaFold, ...] = ()
    meta_evaluation_indices: tuple[int, ...] = ()
    row_ids: np.ndarray | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict(self, predictions: Any) -> np.ndarray:
        """Combine new aligned base predictions with the fitted combiner."""
        if self.combiner is None:
            raise EnsembleError("No ensemble combiner is fitted for kind='none'")
        return np.asarray(self.combiner.predict(predictions), dtype=float)


def _simplex_projection(values: np.ndarray) -> np.ndarray:
    """Project a vector onto the nonnegative unit simplex."""
    sorted_values = np.sort(values)[::-1]
    cumulative = np.cumsum(sorted_values)
    candidates = sorted_values - (cumulative - 1) / (np.arange(len(values)) + 1)
    valid = np.flatnonzero(candidates > 0)
    if not len(valid):
        return np.full(len(values), 1.0 / len(values))
    threshold = candidates[valid[-1]]
    return np.maximum(values - threshold, 0.0)


def _learn_weights(values: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Learn deterministic nonnegative, sum-one weights by projected gradient descent."""
    if values.shape[0] == 0 or not np.isfinite(target).all():
        raise EnsembleError("optimized weights require finite target observations")
    weights = np.full(values.shape[1], 1.0 / values.shape[1])
    gram_norm = float(np.linalg.norm(values, ord=2) ** 2)
    step = 0.5 / max(gram_norm, 1e-12)
    for _ in range(2_000):
        gradient = values.T @ (values @ weights - target) * 2.0
        updated = _simplex_projection(weights - step * gradient)
        if np.max(np.abs(updated - weights)) < 1e-10:
            return updated
        weights = updated
    return weights


def _meta_folds(timestamps: np.ndarray, n_splits: int) -> tuple[MetaFold, ...]:
    """Create deterministic expanding chronological meta folds."""
    if n_splits < 1:
        raise EnsembleError("meta_splits must be at least one")
    order = np.argsort(timestamps, kind="stable")
    sorted_timestamps = timestamps[order]
    group_starts = np.r_[
        0,
        np.flatnonzero(sorted_timestamps[1:] != sorted_timestamps[:-1]) + 1,
    ]
    n_groups = len(group_starts)
    test_groups = n_groups // (n_splits + 1)
    if test_groups < 1:
        raise EnsembleError("insufficient OOS history for chronological meta-cross-fitting")
    initial_groups = n_groups - n_splits * test_groups
    if initial_groups < 1:
        raise EnsembleError("insufficient initial meta-training history")
    folds: list[MetaFold] = []
    for fold in range(n_splits):
        train_group_end = initial_groups + fold * test_groups
        eval_group_end = train_group_end + test_groups
        train_end = group_starts[train_group_end] if train_group_end < n_groups else len(order)
        eval_end = group_starts[eval_group_end] if eval_group_end < n_groups else len(order)
        folds.append(
            MetaFold(
                fold=fold,
                train_indices=tuple(int(i) for i in order[:train_end]),
                evaluation_indices=tuple(int(i) for i in order[train_end:eval_end]),
            )
        )
    return tuple(folds)


def _fit_estimator(template: Any, values: np.ndarray, target: np.ndarray) -> Any:
    """Clone and fit a sklearn-compatible combiner template."""
    if template is None:
        template = Ridge(alpha=1.0)
    fitted = clone(template)
    if not hasattr(fitted, "fit") or not hasattr(fitted, "predict"):
        raise EnsembleError("stacking combiner must implement fit() and predict()")
    fitted.fit(values, target)
    return fitted


@dataclass
class WeightedCombiner:
    """Serializable weighted-average combiner used by fixed/equal/optimized modes."""

    model_names: tuple[str, ...]
    weights: np.ndarray
    allow_missing: bool = False

    def predict(self, predictions: Any) -> np.ndarray:
        """Return the weighted prediction for each input row."""
        values = _align_for_predict(predictions, self.model_names, allow_missing=self.allow_missing)
        if not np.isfinite(values).all() and not self.allow_missing:
            raise EnsembleError("base predictions must be finite at prediction time")
        if self.allow_missing and not np.isfinite(values).all():
            observed = np.isfinite(values)
            denominators = observed @ self.weights
            if np.any(denominators <= 0):
                raise EnsembleError("each prediction row needs one finite base prediction")
            values = np.where(observed, values, 0.0)
            return (values @ self.weights) / denominators
        return values @ self.weights


@dataclass
class StackingCombiner:
    """Serializable sklearn-compatible meta-model over base-model predictions."""

    model_names: tuple[str, ...]
    estimator: Any

    def predict(self, predictions: Any) -> np.ndarray:
        """Return predictions from the fitted meta-estimator."""
        values = _align_for_predict(predictions, self.model_names)
        if not np.isfinite(values).all():
            raise EnsembleError("base predictions must be finite at prediction time")
        return np.asarray(self.estimator.predict(values), dtype=float)


def fit_ensemble(
    config: EnsembleConfig,
    predictions: Any,
) -> EnsembleResult:
    """Fit an ensemble and return final state plus strictly OOS evidence.

    ``predictions`` is the normalized long OOS table produced by training.
    """
    kind = str(config.kind).lower()
    fallback = str(config.fallback).lower()
    try:
        aligned = _normalize_predictions(
            predictions,
            allow_missing=bool(config.allow_missing),
        )
        requested = config.base_models
        if requested is not None:
            unknown = [name for name in requested if name not in aligned.names]
            if unknown:
                raise EnsembleError(f"ensemble references unknown candidates: {unknown}")
            positions = [aligned.names.index(name) for name in requested]
            aligned = AlignedPredictions(
                values=aligned.values[:, positions],
                names=tuple(requested),
                row_ids=aligned.row_ids,
                timestamps=aligned.timestamps,
                target=aligned.target,
            )
        if kind == "none":
            return EnsembleResult(kind="none", model_names=aligned.names, row_ids=aligned.row_ids)
        if kind == "equal_weight":
            weights = np.full(aligned.values.shape[1], 1.0 / aligned.values.shape[1])
        elif kind == "fixed_weight":
            configured = config.weights
            if configured is None:
                raise EnsembleError("fixed_weight requires EnsembleConfig.weights")
            if isinstance(configured, Mapping):
                unknown = set(configured) - set(aligned.names)
                if unknown:
                    raise EnsembleError(
                        f"fixed weights contain unknown candidates: {sorted(unknown)}"
                    )
                raw = np.asarray([configured.get(name, 0.0) for name in aligned.names], dtype=float)
            else:
                raw = np.asarray(configured, dtype=float)
                if raw.ndim != 1 or len(raw) != len(aligned.names):
                    raise EnsembleError("fixed weights must match the number of candidates")
            if not np.isfinite(raw).all() or (raw < 0).any() or raw.sum() <= 0:
                raise EnsembleError("fixed weights must be finite, nonnegative, and nonzero")
            weights = raw / raw.sum()
        if kind in {"equal_weight", "fixed_weight"}:
            combiner = WeightedCombiner(aligned.names, weights, bool(config.allow_missing))
            combined = combiner.predict(aligned.values)
            return EnsembleResult(
                kind=kind,
                model_names=aligned.names,
                combiner=combiner,
                weights=weights,
                oos_predictions=combined,
                meta_oos_predictions=combined,
                meta_evaluation_indices=tuple(range(len(combined))),
                row_ids=aligned.row_ids,
            )
        if kind not in {"optimized_weight", "stacking"}:
            raise EnsembleError(f"unsupported ensemble kind: {kind!r}")
        if aligned.target is None:
            raise EnsembleError(f"{kind} requires realized targets for meta-cross-fitting")
        if not config.allow_missing and not np.isfinite(aligned.values).all():
            raise EnsembleError("learned ensembles require complete finite base predictions")
        valid = np.isfinite(aligned.target) & np.isfinite(aligned.values).all(axis=1)
        if valid.sum() < 2:
            raise EnsembleError("insufficient finite targets for learned ensembling")
        # Keep chronology and row identity intact while dropping unknown-target rows.
        values = aligned.values[valid]
        target = aligned.target[valid]
        valid_rows = np.flatnonzero(valid)
        valid_times = aligned.timestamps[valid]
        n_splits = int(config.meta_splits)
        folds = _meta_folds(valid_times, n_splits)
        meta_oos = np.full(len(values), np.nan, dtype=float)
        for fold in folds:
            train = np.asarray(fold.train_indices, dtype=int)
            evaluation = np.asarray(fold.evaluation_indices, dtype=int)
            if kind == "optimized_weight":
                fold_weights = _learn_weights(values[train], target[train])
                meta_oos[evaluation] = values[evaluation] @ fold_weights
            else:
                fold_estimator = _fit_estimator(config.combiner, values[train], target[train])
                meta_oos[evaluation] = np.asarray(
                    fold_estimator.predict(values[evaluation]), dtype=float
                )
        meta_indices = np.flatnonzero(np.isfinite(meta_oos))
        if not len(meta_indices):
            raise EnsembleError("chronological meta-cross-fitting produced no evaluation rows")
        if kind == "optimized_weight":
            final_weights = _learn_weights(values, target)
            combiner = WeightedCombiner(aligned.names, final_weights, bool(config.allow_missing))
        else:
            final_estimator = _fit_estimator(config.combiner, values, target)
            combiner = StackingCombiner(aligned.names, final_estimator)
        full_oos = np.full(len(aligned.values), np.nan, dtype=float)
        full_oos[valid_rows[meta_indices]] = meta_oos[meta_indices]
        return EnsembleResult(
            kind=kind,
            model_names=aligned.names,
            combiner=combiner,
            weights=getattr(combiner, "weights", None),
            oos_predictions=full_oos,
            meta_oos_predictions=meta_oos[meta_indices],
            meta_folds=folds,
            meta_evaluation_indices=tuple(int(valid_rows[i]) for i in meta_indices),
            row_ids=aligned.row_ids,
            metadata={
                "meta_train_indices": tuple(int(i) for fold in folds for i in fold.train_indices),
                "meta_train_indices_by_fold": tuple(
                    tuple(int(i) for i in fold.train_indices) for fold in folds
                ),
            },
        )
    except EnsembleError as exc:
        if fallback != "none":
            raise
        names = (
            tuple(dict.fromkeys(predictions["candidate"].astype(str)))
            if isinstance(predictions, pd.DataFrame) and "candidate" in predictions
            else ()
        )
        return EnsembleResult(
            kind="none",
            model_names=names,
            fallback_used=True,
            fallback_reason=str(exc),
            metadata={"requested_kind": kind},
        )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

__all__ = [
    "EnsembleError",
    "EnsembleResult",
    "MetaFold",
    "StackingCombiner",
    "WeightedCombiner",
    "fit_ensemble",
]
