"""Flat, validated configuration for reproducible training pipelines.

Usage::

    config = TrainingConfig(
        feature_cols=("x",), target_col="y", timestamp_col="time",
        split=SplitConfig("expanding", 12, 1),
        candidates=(CandidateConfig("ridge", Ridge()),),
        metrics=(MetricConfig("rmse"),),
        selection=SelectionConfig("rmse", "minimize"), random_seed=7,
    )
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

# --------------------------------------------------------------------------- #
# Component configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CandidateConfig:
    """One estimator candidate evaluated with the shared fold plan."""

    name: str
    estimator: Any
    params: Mapping[str, Any] = field(default_factory=dict)
    task: Literal["regression", "binary_classification"] | None = None
    feature_cols: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("candidate name must not be empty")
        if not all(hasattr(self.estimator, method) for method in ("fit", "predict", "get_params")):
            raise TypeError("candidate estimator must be an sklearn-compatible template")
        if self.task not in {None, "regression", "binary_classification"}:
            raise ValueError("unsupported candidate task")
        if self.feature_cols is not None:
            values = tuple(self.feature_cols)
            if not values or len(values) != len(set(values)):
                raise ValueError("candidate feature_cols must be non-empty and unique")
            object.__setattr__(self, "feature_cols", values)
        object.__setattr__(self, "params", dict(self.params))


@dataclass(frozen=True)
class MetricConfig:
    """One OOS metric and its validity requirements."""

    name: str
    direction: Literal["minimize", "maximize"] | None = None
    min_observations: int = 1
    scope: Literal["period", "fold"] | None = None
    base_metric: str | None = None
    statistic: Literal[
        "mean", "dispersion", "hit_rate", "group_count", "observation_count", "min", "max"
    ] = "mean"
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("metric name must not be empty")
        if self.direction not in {None, "minimize", "maximize"}:
            raise ValueError("metric direction must be minimize or maximize")
        if self.min_observations < 1:
            raise ValueError("min_observations must be positive")
        if self.scope is None and self.base_metric is not None:
            raise ValueError("base_metric requires a period or fold scope")
        if self.scope is not None and not self.base_metric:
            raise ValueError("scoped metrics require base_metric")
        object.__setattr__(self, "kwargs", dict(self.kwargs))


@dataclass(frozen=True)
class SplitConfig:
    """Chronological period-window splitting policy.

    ``min_train_periods`` counts usable training periods after gap and purge
    exclusions. ``embargo_periods`` is the explicit pre-evaluation gap.
    """

    kind: Literal["chronological_holdout", "expanding", "rolling", "purged"]
    min_train_periods: int
    eval_periods: int
    step_periods: int | None = None
    train_periods: int | None = None
    embargo_periods: int = 0
    include_partial_final_window: bool = False
    max_folds: int | None = None
    purge_boundary: Literal["strict", "closed"] = "strict"
    first_eval_period: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"chronological_holdout", "expanding", "rolling", "purged"}:
            raise ValueError(f"unsupported split kind: {self.kind}")
        if self.min_train_periods < 1 or self.eval_periods < 1:
            raise ValueError("min_train_periods and eval_periods must be positive")
        if self.step_periods is not None and self.step_periods < 1:
            raise ValueError("step_periods must be positive when configured")
        if self.train_periods is not None and self.train_periods < 1:
            raise ValueError("train_periods must be positive when configured")
        if self.embargo_periods < 0:
            raise ValueError("embargo_periods must be nonnegative")
        if self.max_folds is not None and self.max_folds < 1:
            raise ValueError("max_folds must be positive when configured")
        if self.purge_boundary not in {"strict", "closed"}:
            raise ValueError("purge_boundary must be strict or closed")
        if self.first_eval_period is not None and (
            isinstance(self.first_eval_period, bool)
            or not isinstance(self.first_eval_period, int)
            or self.first_eval_period < 0
        ):
            raise ValueError("first_eval_period must be a nonnegative integer when configured")
        if self.kind != "purged" and self.purge_boundary != "strict":
            raise ValueError("purge_boundary is configurable only for purged splits")
        if self.kind != "purged" and self.first_eval_period is not None:
            raise ValueError("first_eval_period is configurable only for purged splits")
        if self.kind == "rolling" and self.train_periods is None:
            raise ValueError("rolling splits require train_periods")


@dataclass(frozen=True)
class PreprocessingConfig:
    """Ordered numeric preprocessing and inference schema policies."""

    impute_strategy: Literal["mean", "median", "most_frequent", "constant"] | None = None
    impute_fill_value: float = 0.0
    scale: Literal["standard", "minmax", "robust", "maxabs"] | None = None
    clip_min: float | Mapping[str, float] | tuple[float, ...] | None = None
    clip_max: float | Mapping[str, float] | tuple[float, ...] | None = None
    winsorize: tuple[float, float] | None = None
    max_features: int | None = None
    missing_policy: Literal["error", "allow"] = "error"
    extra_columns: Literal["ignore", "error"] = "ignore"

    def __post_init__(self) -> None:
        if self.impute_strategy not in {None, "mean", "median", "most_frequent", "constant"}:
            raise ValueError("unsupported impute_strategy")
        if self.scale not in {None, "standard", "minmax", "robust", "maxabs"}:
            raise ValueError("unsupported scale")
        if self.winsorize is not None:
            lower, upper = self.winsorize
            if not 0 <= lower < upper <= 1:
                raise ValueError("winsorize bounds must satisfy 0 <= lower < upper <= 1")
        if self.max_features is not None and self.max_features < 1:
            raise ValueError("max_features must be positive when configured")


@dataclass(frozen=True)
class SelectionConfig:
    """OOS-only model eligibility and deterministic ranking policy."""

    primary_metric: str
    direction: Literal["minimize", "maximize"]
    min_coverage: float = 0.0
    min_folds: int = 0
    max_instability: float | None = None
    max_loss: float | None = None
    tie_break_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.primary_metric:
            raise ValueError("primary_metric must not be empty")
        if self.direction not in {"minimize", "maximize"}:
            raise ValueError("selection direction must be minimize or maximize")
        if not 0 <= self.min_coverage <= 1:
            raise ValueError("min_coverage must be between zero and one")
        if self.min_folds < 0:
            raise ValueError("min_folds must be nonnegative")
        object.__setattr__(self, "tie_break_fields", tuple(self.tie_break_fields))


@dataclass(frozen=True)
class EnsembleConfig:
    """Policy for combining selected candidate OOS predictions."""

    kind: Literal["none", "equal_weight", "fixed_weight", "optimized_weight", "stacking"] = "none"
    weights: Mapping[str, float] | None = None
    meta_splits: int = 3
    combiner: Any = None
    fallback: Literal["error", "none"] = "error"
    allow_missing: bool = False
    base_models: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.kind not in {
            "none",
            "equal_weight",
            "fixed_weight",
            "optimized_weight",
            "stacking",
        }:
            raise ValueError(f"unsupported ensemble kind: {self.kind}")
        if self.meta_splits < 2:
            raise ValueError("meta_splits must be at least two")
        if self.kind == "fixed_weight" and not self.weights:
            raise ValueError("fixed_weight ensembles require weights")
        if self.weights is not None:
            object.__setattr__(self, "weights", dict(self.weights))
        if self.base_models is not None:
            object.__setattr__(self, "base_models", tuple(self.base_models))


# --------------------------------------------------------------------------- #
# Complete training configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TrainingConfig:
    """Complete reproducible configuration for one supervised training run."""

    feature_cols: tuple[str, ...]
    target_col: str
    timestamp_col: str
    split: SplitConfig
    candidates: tuple[CandidateConfig, ...]
    metrics: tuple[MetricConfig, ...]
    selection: SelectionConfig
    random_seed: int
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    ensemble: EnsembleConfig = field(default_factory=EnsembleConfig)
    task: Literal["regression", "binary_classification"] = "regression"
    row_id_col: str | None = None
    entity_col: str | None = None
    period_col: str | None = None
    target_end_col: str | None = None
    prediction_transform: Any = None
    training_cutoff: Any = None
    weight_col: str | None = None
    final_refit: bool = True
    keep_fold_models: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_cols", tuple(self.feature_cols))
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "metrics", tuple(self.metrics))
        self.validate()

    def validate(self) -> None:
        """Fail closed on inconsistent configuration before inspecting data."""

        if not self.feature_cols or len(self.feature_cols) != len(set(self.feature_cols)):
            raise ValueError("feature_cols must be non-empty and unique")
        columns = (
            self.target_col,
            self.timestamp_col,
            self.row_id_col,
            self.entity_col,
            self.period_col,
            self.target_end_col,
            self.weight_col,
        )
        if any(value is not None and not value for value in columns):
            raise ValueError("configured column names must not be empty")
        if self.target_col in self.feature_cols or self.timestamp_col in self.feature_cols:
            raise ValueError("target_col and timestamp_col must not be feature columns")
        if self.weight_col in {*self.feature_cols, self.target_col, self.timestamp_col}:
            raise ValueError("weight_col must not be a feature, target, or timestamp column")
        if not self.candidates:
            raise ValueError("candidates must not be empty")
        names = tuple(candidate.name for candidate in self.candidates)
        if len(names) != len(set(names)):
            raise ValueError("candidate names must be unique")
        if not self.metrics:
            raise ValueError("metrics must not be empty")
        if self.selection.primary_metric not in {metric.name for metric in self.metrics}:
            raise ValueError("selection primary_metric must be configured in metrics")
        if self.split.kind == "purged" and self.target_end_col is None:
            raise ValueError("purged splits require target_end_col")
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")
        if not isinstance(self.final_refit, bool):
            raise TypeError("final_refit must be a boolean")
        if not isinstance(self.keep_fold_models, bool):
            raise TypeError("keep_fold_models must be a boolean")


# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #


__all__ = [
    "CandidateConfig",
    "EnsembleConfig",
    "MetricConfig",
    "PreprocessingConfig",
    "SelectionConfig",
    "SplitConfig",
    "TrainingConfig",
]
