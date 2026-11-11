"""Score supplied OOS predictions from independently fitted single-feature models.

Usage: ``single_feature_importance(predictions, model_features=models,
scorer=score, score_name="accuracy", greater_is_better=True, heldout=True,
evaluation_provenance="training-run/folds")``. This function never fits models.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result contract
# --------------------------------------------------------------------------- #
from dataclasses import dataclass

import numpy as np
import polars as pl

from . import _moments
from .permutation import Scorer, _columns, _evaluation_metadata, _name, _score, _validate_evaluation_rows


@dataclass(frozen=True)
class SingleFeatureImportanceResult:
    """Unmodified prediction records, fold scores, and descriptive summaries."""

    predictions: pl.DataFrame
    raw: pl.DataFrame
    summary: pl.DataFrame


# --------------------------------------------------------------------------- #
# Public OOS single-feature scoring
# --------------------------------------------------------------------------- #


def single_feature_importance(
    predictions: pl.DataFrame,
    *,
    model_features: pl.DataFrame,
    scorer: Scorer,
    score_name: str,
    greater_is_better: bool,
    heldout: bool,
    evaluation_provenance: str,
) -> SingleFeatureImportanceResult:
    """Score every feature on identical evaluation observations within each fold.

    ``model_features`` declares partition_id, model_id, and feature_columns
    (List[String]). Exactly one declared training feature must match each
    prediction record's feature. This checks declarations and alignment, not
    whether the producer really isolated fitting/preprocessing from evaluation.
    Scalar predictions support regression, binary probabilities, or numeric labels;
    multiclass probability vectors are deliberately outside this table contract.
    """
    _evaluation_metadata(heldout, evaluation_provenance, score_name, greater_is_better)
    keys = {"partition_id": pl.String, "model_id": pl.String}
    _columns(predictions, {**keys, "feature": pl.String, "prediction": pl.Float64})
    _columns(model_features, {**keys, "feature_columns": pl.List(pl.String)})
    if predictions.height == 0 or model_features.height == 0:
        raise ValueError("predictions and model_features must not be empty")
    for frame, columns in (
        (predictions, ("feature", "partition_id", "model_id")),
        (model_features, ("partition_id", "model_id")),
    ):
        for column in columns:
            for value in frame[column].unique().to_list():
                _name(value, column)
    declarations = {}
    for partition, model, features in model_features.select("partition_id", "model_id", "feature_columns").iter_rows():
        if (partition, model) in declarations:
            raise ValueError("model_features keys must be unique")
        if features is None or len(features) != 1:
            raise ValueError("SFI requires exactly one independently fitted feature per model")
        _name(features[0], "declared feature")
        declarations[(partition, model)] = features[0]
    observed = set()
    raw_rows = []
    feature_set = set(predictions["feature"].to_list())
    for (partition,), partition_rows in predictions.partition_by("partition_id", as_dict=True).items():
        if set(partition_rows["feature"].to_list()) != feature_set:
            raise ValueError("all features must have predictions in every partition")
        alignment = None
        for (feature,), rows in partition_rows.partition_by("feature", as_dict=True).items():
            rows = rows.sort("observation_id")
            _validate_evaluation_rows(rows)
            models = rows["model_id"].unique().to_list()
            if len(models) != 1:
                raise ValueError("one model is required per feature and partition")
            model = models[0]
            observed.add((partition, model))
            if declarations.get((partition, model)) != feature:
                raise ValueError("prediction feature does not match the declared single model feature")
            aligned = rows.select("observation_id", "decision_time", "target", "sample_weight")
            if alignment is None:
                alignment = aligned
            elif not aligned.equals(alignment):
                raise ValueError("SFI features must share exact evaluation IDs, timestamps, targets, and weights")
            score, status = _score(
                rows["target"].to_numpy(), rows["prediction"].to_numpy(), rows["sample_weight"].to_numpy(), scorer
            )
            raw_rows.append(
                (
                    feature,
                    partition,
                    model,
                    evaluation_provenance,
                    score_name,
                    greater_is_better,
                    score,
                    rows.height,
                    float(rows["sample_weight"].sum()),
                    status,
                )
            )
    if set(declarations) != observed:
        raise ValueError("model_features must match supplied prediction models exactly")
    raw = pl.DataFrame(
        raw_rows,
        schema={
            "feature": pl.String,
            "partition_id": pl.String,
            "model_id": pl.String,
            "evaluation_provenance": pl.String,
            "score_name": pl.String,
            "greater_is_better": pl.Boolean,
            "importance": pl.Float64,
            "n_observations": pl.UInt64,
            "weight_sum": pl.Float64,
            "status": pl.String,
        },
        orient="row",
    ).sort("feature", "partition_id")
    summary_rows = []
    for (feature,), rows in raw.partition_by("feature", as_dict=True).items():
        values = rows["importance"].drop_nulls().to_numpy()
        mean, std = _moments(values, ddof=0)
        scaled = std / np.sqrt(rows.height) if std is not None else None
        status = "ok" if len(values) == rows.height else ("partial" if len(values) else "undefined")
        summary_rows.append(
            (feature, score_name, greater_is_better, mean, std, scaled, rows.height, len(values), status)
        )
    return SingleFeatureImportanceResult(
        predictions=predictions.clone(),
        raw=raw,
        summary=pl.DataFrame(
            summary_rows,
            schema={
                "feature": pl.String,
                "score_name": pl.String,
                "greater_is_better": pl.Boolean,
                "importance": pl.Float64,
                "fold_population_std": pl.Float64,
                "scaled_fold_dispersion": pl.Float64,
                "n_partitions": pl.UInt64,
                "n_valid": pl.UInt64,
                "status": pl.String,
            },
            orient="row",
        ),
    )
