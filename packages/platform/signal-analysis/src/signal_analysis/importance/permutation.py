"""Measure held-out score loss after permuting explicitly chosen feature columns.

Usage: ``permutation_importance(heldout, feature_columns=["x"], predict=predict,
scorer=score, score_name="accuracy", greater_is_better=True, model_id="m",
partition_id="p", heldout=True, evaluation_provenance="run/fold", repetitions=8,
seed=7, normalization="raw")``. No fitting occurs here.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports, scalar scoring, and result contract
# --------------------------------------------------------------------------- #
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray

from signal_analysis.contracts import validate_feature_panel

from . import _moments

Array = NDArray[np.float64]
Scorer = Callable[[Array, Array, Array], float]


@dataclass(frozen=True)
class PermutationImportanceResult:
    """One partition's repetition values and descriptive repetition summaries."""

    raw: pl.DataFrame
    summary: pl.DataFrame


def _name(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty trimmed string")


def _evaluation_metadata(heldout: bool, evaluation_provenance: str, score_name: str, greater_is_better: bool) -> None:
    if heldout is not True:
        raise ValueError("heldout=True must explicitly declare externally held-out predictions")
    _name(evaluation_provenance, "evaluation_provenance")
    _name(score_name, "score_name")
    if not isinstance(greater_is_better, bool):
        raise ValueError("greater_is_better must be boolean")


def _columns(frame: pl.DataFrame, schema: dict[str, pl.DataType | type[pl.DataType]]) -> None:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("expected a Polars DataFrame")
    for name, dtype in schema.items():
        if name not in frame or frame.schema[name] != dtype:
            raise ValueError(f"{name} must have dtype {dtype}")


def _score(y: Array, prediction: Array, weights: Array, scorer: Scorer) -> tuple[float | None, str]:
    if prediction.ndim not in (1, 2) or len(prediction) != len(y):
        raise ValueError("predict must return one prediction row per held-out observation")
    if not np.isfinite(prediction).all():
        return None, "invalid_prediction"
    if weights.sum() == 0:
        return None, "zero_weight"
    # Defensive copies prevent callbacks from changing subsequent evaluations.
    value = float(scorer(y.copy(), prediction.copy(), weights.copy()))
    return (value, "ok") if np.isfinite(value) else (None, "undefined_score")


def _validate_evaluation_rows(frame: pl.DataFrame) -> None:
    _columns(
        frame,
        {
            "observation_id": pl.String,
            "decision_time": pl.Datetime("us", "UTC"),
            "target": pl.Float64,
            "sample_weight": pl.Float64,
        },
    )
    if frame.height == 0:
        raise ValueError("held-out observations must not be empty")
    ids = frame["observation_id"].to_list()
    if any(not value or value != value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("observation_id must be nonempty, unique, and trimmed")
    if frame["decision_time"].null_count():
        raise ValueError("decision_time must be non-null")
    for name in ("target", "sample_weight"):
        if frame[name].null_count() or not frame[name].is_finite().all():
            raise ValueError(f"{name} must be complete and finite")
    if (frame["sample_weight"] < 0).any():
        raise ValueError("sample_weight must be nonnegative")
    if not np.isfinite(frame["sample_weight"].sum()):
        raise ValueError("sample_weight sum must be finite")


# --------------------------------------------------------------------------- #
# Public held-out permutation operation
# --------------------------------------------------------------------------- #


def permutation_importance(
    observations: pl.DataFrame,
    *,
    feature_columns: Sequence[str],
    predict: Callable[[Array], Array],
    scorer: Scorer,
    score_name: str,
    greater_is_better: bool,
    model_id: str,
    partition_id: str,
    heldout: bool,
    evaluation_provenance: str,
    repetitions: int,
    seed: int,
    normalization: Literal["raw", "afml_relative"],
    score_optimum: float | None = None,
    feature_groups: Mapping[str, Sequence[str]] | None = None,
) -> PermutationImportanceResult:
    """Permute rows jointly for each declared feature group, within one test fold.

    The same row permutation is applied to all columns in a group. There is no
    row stratification, blocking, or cross-partition mixing. Input rows are
    canonicalized by observation_id before a local seeded generator is used.
    The scorer receives target, prediction, and observation weights in that order.
    AFML-relative importance divides the directed score decrease by the directed
    gap from the permuted score to an explicitly supplied optimal score.
    """
    validate_feature_panel(observations, feature_columns=feature_columns)
    if set(feature_columns) & {"target", "sample_weight"}:
        raise ValueError("target and sample_weight are evaluation metadata, not feature columns")
    _validate_evaluation_rows(observations)
    _evaluation_metadata(heldout, evaluation_provenance, score_name, greater_is_better)
    _name(model_id, "model_id")
    _name(partition_id, "partition_id")
    for value, label, minimum in ((repetitions, "repetitions", 1), (seed, "seed", 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{label} must be an integer >= {minimum}")
    if seed >= 2**64:
        raise ValueError("seed must be smaller than 2**64")
    if normalization not in {"raw", "afml_relative"}:
        raise ValueError("unsupported normalization")
    if normalization == "afml_relative" and (score_optimum is None or not np.isfinite(score_optimum)):
        raise ValueError("afml_relative requires a finite score_optimum")
    if normalization == "raw" and score_optimum is not None:
        raise ValueError("score_optimum is only meaningful for afml_relative")
    frame = observations.sort("observation_id")
    x = frame.select(feature_columns).to_numpy()
    if not np.isfinite(x).all():
        raise ValueError("held-out features must be complete and finite; preprocessing belongs to the caller")
    groups = dict(feature_groups) if feature_groups is not None else {name: (name,) for name in feature_columns}
    if not groups:
        raise ValueError("feature_groups must not be empty")
    for name, columns in groups.items():
        _name(name, "feature group")
        if (
            isinstance(columns, str)
            or not columns
            or len(columns) != len(set(columns))
            or any(column not in feature_columns for column in columns)
        ):
            raise ValueError("feature groups must contain unique declared feature columns")
    y, weights = frame["target"].to_numpy(), frame["sample_weight"].to_numpy()
    baseline, baseline_status = _score(y, np.asarray(predict(x.copy()), dtype=float), weights, scorer)
    direction = 1 if greater_is_better else -1
    rng = np.random.default_rng(seed)
    raw_rows, summary_rows = [], []
    for group in sorted(groups):
        columns = list(groups[group])
        indices = [list(feature_columns).index(name) for name in columns]
        importances = []
        for repetition in range(repetitions):
            order = rng.permutation(len(y))
            changed = x.copy()
            changed[:, indices] = x[order][:, indices]
            permuted, status = _score(y, np.asarray(predict(changed), dtype=float), weights, scorer)
            decrease, denominator, importance = None, None, None
            if baseline is None:
                status = f"baseline_{baseline_status}"
            elif permuted is not None:
                decrease = direction * (baseline - permuted)
                if not np.isfinite(decrease):
                    decrease, status = None, "nonfinite_decrease"
                elif normalization == "raw":
                    importance = decrease
                else:
                    assert score_optimum is not None
                    denominator = direction * (score_optimum - permuted)
                    if direction * (score_optimum - baseline) < 0 or denominator < 0:
                        status = "score_exceeds_optimum"
                    elif denominator == 0:
                        status = "zero_normalization_denominator"
                    elif not np.isfinite(denominator):
                        denominator, status = None, "nonfinite_normalization_denominator"
                    else:
                        importance = decrease / denominator
                        if not np.isfinite(importance):
                            importance, status = None, "nonfinite_importance"
            if importance is not None:
                importances.append(importance)
            raw_rows.append(
                (
                    group,
                    columns,
                    partition_id,
                    model_id,
                    evaluation_provenance,
                    score_name,
                    greater_is_better,
                    normalization,
                    score_optimum,
                    seed,
                    repetition,
                    baseline,
                    permuted,
                    decrease,
                    denominator,
                    importance,
                    status,
                    len(y),
                    float(weights.sum()),
                    frame["observation_id"].to_list(),
                    order.tolist(),
                )
            )
        mean, std = _moments(np.asarray(importances, dtype=float), ddof=1)
        status = "ok" if len(importances) == repetitions else ("partial" if importances else "undefined")
        summary_rows.append(
            (
                group,
                partition_id,
                model_id,
                score_name,
                greater_is_better,
                normalization,
                mean,
                std,
                repetitions,
                len(importances),
                status,
            )
        )
    return PermutationImportanceResult(
        raw=pl.DataFrame(
            raw_rows,
            schema={
                "feature": pl.String,
                "permuted_columns": pl.List(pl.String),
                "partition_id": pl.String,
                "model_id": pl.String,
                "evaluation_provenance": pl.String,
                "score_name": pl.String,
                "greater_is_better": pl.Boolean,
                "normalization": pl.String,
                "score_optimum": pl.Float64,
                "seed": pl.UInt64,
                "repetition": pl.UInt64,
                "baseline_score": pl.Float64,
                "permuted_score": pl.Float64,
                "raw_decrease": pl.Float64,
                "normalization_denominator": pl.Float64,
                "importance": pl.Float64,
                "status": pl.String,
                "n_observations": pl.UInt64,
                "weight_sum": pl.Float64,
                "observation_ids": pl.List(pl.String),
                "permutation_indices": pl.List(pl.UInt64),
            },
            orient="row",
        ),
        summary=pl.DataFrame(
            summary_rows,
            schema={
                "feature": pl.String,
                "partition_id": pl.String,
                "model_id": pl.String,
                "score_name": pl.String,
                "greater_is_better": pl.Boolean,
                "normalization": pl.String,
                "importance": pl.Float64,
                "repetition_sample_std": pl.Float64,
                "n_repetitions": pl.UInt64,
                "n_valid": pl.UInt64,
                "status": pl.String,
            },
            orient="row",
        ),
    )
