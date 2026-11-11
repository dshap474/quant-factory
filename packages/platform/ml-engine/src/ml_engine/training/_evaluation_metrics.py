"""Private metric primitives used by :mod:`ml_engine.training.evaluation`.

This module has no public package export.  It keeps scalar metric computation
and period/fold aggregation separate from the OOS result and orchestration
types.

Usage::

    result = compute_base("rmse", rows, "prediction", "minimize", 1)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, roc_auc_score

# --------------------------------------------------------------------------- #
# Metric specifications and values
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MetricResult:
    """One scalar metric and its explicit validity state."""

    name: str
    value: float | None
    direction: str
    n_observations: int
    min_observations: int
    defined: bool
    reason: str | None = None


_LOSS_NAMES = {"mae", "mse", "rmse", "log_loss"}
_DISALLOWED_NAMES = {
    "sharpe",
    "sharpe_ratio",
    "drawdown",
    "max_drawdown",
    "turnover",
    "pnl",
    "profit_factor",
    "returns",
    "information_coefficient",
    "information_ratio",
    "ic",
    "ic_mean",
    "ic_std",
}
_BASE_ALIASES = {
    "mean_absolute_error": "mae",
    "mean_squared_error": "mse",
    "root_mean_squared_error": "rmse",
    "logloss": "log_loss",
    "rocauc": "roc_auc",
    "roc_auc_score": "roc_auc",
    "pearson_correlation": "pearson",
    "spearman_correlation": "spearman",
    "spearman_rank_correlation": "spearman",
    "correlation": "pearson",
}


def normal_name(value: Any) -> str:
    """Normalize enum/string metric names without changing their meaning."""

    value = getattr(value, "value", value)
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _field(config: Any, *names: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return next((config[name] for name in names if name in config), default)
    return next((getattr(config, name) for name in names if hasattr(config, name)), default)


def metric_spec(config: Any) -> tuple[str, str, str, dict[str, Any]]:
    """Normalize a MetricConfig-like object for evaluation."""

    raw_name = _field(config, "name", default=config)
    requested = normal_name(raw_name)
    options = dict(_field(config, "kwargs", default={}) or {})
    for name in ("scope", "base_metric", "statistic"):
        value = _field(config, name, default=None)
        if value is not None:
            options[name] = value

    canonical = _BASE_ALIASES.get(requested, requested)
    if canonical in _DISALLOWED_NAMES:
        raise ValueError(f"financial metric {requested!r} is outside ml-engine")
    direction = _field(config, "direction", default=None)
    direction = normal_name(direction) if direction is not None else ""
    if direction in {"max", "higher", "maximize"}:
        direction = "maximize"
    elif direction in {"min", "lower", "minimize"}:
        direction = "minimize"
    elif direction:
        raise ValueError(f"metric direction must be maximize or minimize, got {direction!r}")
    else:
        direction = "minimize" if canonical in _LOSS_NAMES else "maximize"
        if "dispersion" in canonical or canonical.endswith("_std"):
            direction = "minimize"

    minimum = _field(
        config,
        "min_observations",
        default=1,
    )
    if minimum is None:
        minimum = 1
    try:
        minimum = int(minimum)
    except (TypeError, ValueError) as exc:
        raise TypeError("metric minimum observations must be an integer") from exc
    if minimum < 1:
        raise ValueError("metric minimum observations must be at least one")
    return requested, canonical, direction, {**options, "min_observations": minimum}


def parse_summary_name(name: str, options: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """Return the explicit grouped-metric contract, when configured."""

    del name
    scope = options.get("scope")
    if scope is None:
        return None
    if scope not in {"period", "fold"}:
        raise ValueError("metric scope must be 'period' or 'fold'")
    base = normal_name(options.get("base_metric"))
    statistic = normal_name(options.get("statistic", "mean"))
    return scope, _BASE_ALIASES.get(base, base), statistic


# --------------------------------------------------------------------------- #
# Input normalization and scalar built-ins
# --------------------------------------------------------------------------- #


def prediction_column(rows: pd.DataFrame) -> str:
    """Find the normalized prediction column or fail clearly."""

    for name in ("prediction", "predictions", "y_pred", "pred"):
        if name in rows.columns:
            return name
    raise ValueError("OOS predictions require a prediction column")


def valid_rows(rows: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Validate required columns, uniqueness, and observed target rows."""

    if not isinstance(rows, pd.DataFrame):
        raise TypeError("OOS predictions must be a pandas DataFrame")
    prediction = prediction_column(rows)
    if "target" not in rows.columns and "y_true" not in rows.columns:
        raise ValueError("OOS predictions require a target column")
    frame = rows.copy()
    if "target" not in frame.columns:
        frame = frame.rename(columns={"y_true": "target"})
    if "row_id" in frame.columns:
        identity = ["row_id"] + (["candidate"] if "candidate" in frame.columns else [])
        if frame.duplicated(identity).any():
            raise ValueError("OOS predictions must contain at most one row per row_id/candidate")
    return frame.loc[frame["target"].notna() & frame[prediction].notna()].copy(), prediction


def numeric_pair(rows: pd.DataFrame, prediction: str) -> tuple[np.ndarray, np.ndarray] | None:
    predicted = pd.to_numeric(rows[prediction], errors="coerce")
    target = pd.to_numeric(rows["target"], errors="coerce")
    valid = predicted.notna() & target.notna()
    if not valid.any():
        return None
    pred = predicted.loc[valid].to_numpy(dtype=float)
    truth = target.loc[valid].to_numpy(dtype=float)
    finite = np.isfinite(pred) & np.isfinite(truth)
    return (pred[finite], truth[finite]) if finite.any() else None


def undefined(name: str, direction: str, n: int, minimum: int, reason: str) -> MetricResult:
    return MetricResult(name, None, direction, n, minimum, False, reason)


def _classification_labels(
    target: pd.Series, prediction: pd.Series
) -> tuple[np.ndarray, np.ndarray]:
    truth = target.to_numpy()
    numeric = pd.to_numeric(prediction, errors="coerce")
    classes = pd.unique(target.dropna())
    if len(classes) == 2 and numeric.notna().all():
        values = numeric.to_numpy(dtype=float)
        if np.isfinite(values).all() and np.all((values >= 0) & (values <= 1)):
            ordered = np.sort(classes)
            return truth, np.where(values >= 0.5, ordered[1], ordered[0])
    return truth, prediction.to_numpy()


def compute_base(
    name: str,
    rows: pd.DataFrame,
    prediction: str,
    direction: str,
    minimum: int,
    *,
    metric_name: str | None = None,
    custom: Any = None,
) -> MetricResult:
    """Compute one built-in/custom metric, preserving undefined state."""

    metric_name = metric_name or name
    numeric_names = {"mae", "mse", "rmse", "pearson", "spearman"}
    numeric = numeric_pair(rows, prediction) if name in numeric_names else None
    n = len(numeric[0]) if numeric is not None else len(rows)
    if n < minimum:
        return undefined(metric_name, direction, n, minimum, "fewer than min_observations")
    try:
        if name in {"mae", "mse", "rmse"}:
            if numeric is None:
                return undefined(metric_name, direction, n, minimum, "non-numeric observations")
            pred, truth = numeric
            error = pred - truth
            if name == "mae":
                value = np.mean(np.abs(error))
            else:
                value = np.mean(error**2)
                if name == "rmse":
                    value = np.sqrt(value)
        elif name in {"pearson", "spearman"}:
            if numeric is None:
                return undefined(metric_name, direction, n, minimum, "non-numeric observations")
            pred, truth = numeric
            if np.ptp(pred) == 0 or np.ptp(truth) == 0:
                return undefined(metric_name, direction, n, minimum, "constant input")
            value = pd.Series(pred).corr(
                pd.Series(truth),
                method="pearson" if name == "pearson" else "spearman",
            )
        elif name in {"accuracy", "balanced_accuracy"}:
            truth, pred = _classification_labels(rows["target"], rows[prediction])
            value = (
                accuracy_score(truth, pred)
                if name == "accuracy"
                else balanced_accuracy_score(truth, pred)
            )
        elif name == "log_loss":
            truth = rows["target"].to_numpy()
            raw = rows[prediction].to_numpy()
            if (
                raw.ndim == 1
                and raw.dtype == object
                and any(isinstance(item, (list, tuple, np.ndarray)) for item in raw)
            ):
                raw = np.asarray(list(raw), dtype=float)
            probabilities = np.asarray(raw, dtype=float)
            if probabilities.ndim == 1:
                if len(pd.unique(truth)) != 2:
                    return undefined(
                        metric_name,
                        direction,
                        n,
                        minimum,
                        "one-dimensional probabilities require binary targets",
                    )
                if not np.isfinite(probabilities).all() or np.any(
                    (probabilities < 0) | (probabilities > 1)
                ):
                    return undefined(
                        metric_name, direction, n, minimum, "probabilities outside [0, 1]"
                    )
            elif probabilities.ndim == 2:
                if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
                    return undefined(
                        metric_name, direction, n, minimum, "invalid class probabilities"
                    )
                sums = probabilities.sum(axis=1)
                if np.any(sums <= 0):
                    return undefined(
                        metric_name, direction, n, minimum, "probability row sums must be positive"
                    )
                probabilities = probabilities / sums[:, None]
            else:
                return undefined(
                    metric_name, direction, n, minimum, "probability shape is not supported"
                )
            value = log_loss(truth, probabilities, labels=np.sort(pd.unique(truth)))
        elif name == "roc_auc":
            truth = rows["target"].to_numpy()
            if len(pd.unique(truth)) < 2:
                return undefined(metric_name, direction, n, minimum, "ROC AUC requires two classes")
            score = pd.to_numeric(rows[prediction], errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(score).all():
                return undefined(metric_name, direction, n, minimum, "non-finite scores")
            value = roc_auc_score(truth, score)
        elif custom is not None:
            value = custom(rows["target"].to_numpy(), rows[prediction].to_numpy())
        else:
            return undefined(metric_name, direction, n, minimum, f"unknown metric {name!r}")
    except (TypeError, ValueError, FloatingPointError) as exc:
        return undefined(metric_name, direction, n, minimum, str(exc))
    value = float(value)
    return (
        undefined(metric_name, direction, n, minimum, "metric result is non-finite")
        if not np.isfinite(value)
        else MetricResult(metric_name, value, direction, n, minimum, True)
    )


# --------------------------------------------------------------------------- #
# Grouped summaries
# --------------------------------------------------------------------------- #


def _hit_rate(rows: pd.DataFrame, prediction: str) -> float | None:
    numeric = numeric_pair(rows, prediction)
    if numeric is not None:
        pred, truth = numeric
        classes = set(np.unique(truth))
        if classes.issubset({0.0, 1.0}) and len(classes) == 2:
            return float(np.mean((pred >= 0.5) == truth))
        return float(np.mean(((pred > 0) & (truth > 0)) | ((pred < 0) & (truth < 0))))
    if rows.empty:
        return None
    truth, pred = _classification_labels(rows["target"], rows[prediction])
    try:
        value = float(accuracy_score(truth, pred))
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def group_frame(
    rows: pd.DataFrame, prediction: str, group_col: str | None, base_names: set[str]
) -> pd.DataFrame:
    """Compute row-aligned metric values for each period or fold."""

    if group_col is None or group_col not in rows.columns:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for key, group in rows.groupby(group_col, sort=False, dropna=False):
        record: dict[str, Any] = {group_col: key, "n_observations": len(group)}
        for base in sorted(base_names):
            result = compute_base(base, group, prediction, "maximize", 1)
            record[base] = result.value
            record[f"{base}_defined"] = result.defined
        record["hit_rate"] = _hit_rate(group, prediction)
        records.append(record)
    return pd.DataFrame.from_records(records)


def aggregate_group_metric(
    requested: str,
    base: str,
    statistic: str,
    groups: pd.DataFrame,
    total_observations: int,
    direction: str,
    minimum: int,
) -> MetricResult:
    """Aggregate per-group metric values without substituting undefined data."""

    if groups.empty:
        return undefined(requested, direction, total_observations, minimum, "no period/fold groups")
    statistic = normal_name(statistic)
    if statistic in {"std", "dispersion", "stability", "sd"}:
        statistic = "dispersion"
    elif statistic in {"count", "group_count", "n_groups"}:
        statistic = "group_count"
    elif statistic in {"observation_count", "observations", "n"}:
        statistic = "observation_count"
    elif statistic in {"hit", "hit_rate", "accuracy"}:
        statistic = "hit_rate"
    elif statistic not in {"mean", "min", "max"}:
        return undefined(
            requested,
            direction,
            total_observations,
            minimum,
            f"unknown summary statistic {statistic!r}",
        )
    if statistic == "group_count":
        value = float(len(groups))
    elif statistic == "observation_count":
        value = float(groups["n_observations"].sum())
    elif statistic == "hit_rate":
        values = pd.to_numeric(groups["hit_rate"], errors="coerce").dropna()
        if values.empty:
            return undefined(
                requested, direction, total_observations, minimum, "undefined group hit rates"
            )
        value = float(values.mean())
    else:
        if base not in groups:
            return undefined(
                requested, direction, total_observations, minimum, f"unknown group metric {base!r}"
            )
        values = pd.to_numeric(groups[base], errors="coerce").dropna()
        if values.empty:
            return undefined(
                requested, direction, total_observations, minimum, "undefined group metrics"
            )
        value = float(
            {"mean": values.mean, "dispersion": values.std, "min": values.min, "max": values.max}[
                statistic
            ]()
        )
    return (
        undefined(requested, direction, total_observations, minimum, "summary result is non-finite")
        if not np.isfinite(value)
        else MetricResult(requested, value, direction, total_observations, minimum, True)
    )


__all__ = [
    "MetricResult",
    "aggregate_group_metric",
    "compute_base",
    "group_frame",
    "metric_spec",
    "normal_name",
    "parse_summary_name",
    "valid_rows",
]
