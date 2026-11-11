"""Explicit supervised training orchestration for tabular data.

Usage::

    config = TrainingConfig(...)
    result = TrainingPipeline(config).run(training_frame)

The pipeline owns the order of validation, fold-local fitting, OOS evaluation,
selection, optional ensembling, and final refitting.  Model artifacts are only
written via an explicit :meth:`TrainingResult.save`; every run additionally
registers a best-effort JSON status sidecar through
:class:`~ml_engine.training.run.AutoTrackingContext` (suppress with
``ML_ENGINE_TRACKING=0``). Sidecar failures are recorded on
``TrainingResult.warnings`` and do not fail training.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from .config import CandidateConfig, EnsembleConfig, TrainingConfig
from .ensemble import EnsembleResult, fit_ensemble
from .evaluation import EvaluationSummary, evaluate_candidates, evaluate_oos
from .methodologies import (
    Fold,
    build_holdout_plan,
    build_walk_forward_plan,
    fit_full_data,
)
from .progress import TrainingProgress, TrainingStage
from .result import TrainingResult
from .run import AutoTrackingContext
from .selection import SelectionReport, select_candidate
from .validation import PreparedData, validate_training_data

# --------------------------------------------------------------------------- #
# Internal fitted-state helpers
# --------------------------------------------------------------------------- #


def _feature_cols(config: TrainingConfig, candidate: CandidateConfig) -> tuple[str, ...]:
    """Resolve an optional candidate feature subset in declaration order."""
    configured = config.feature_cols
    values = candidate.feature_cols if candidate.feature_cols is not None else configured
    if not values or len(set(values)) != len(values):
        raise ValueError("Candidate feature subset must be non-empty and unique")
    unknown = [name for name in values if name not in configured]
    if unknown:
        raise ValueError(f"Candidate feature subset contains unknown features: {unknown}")
    return values


def _oos_row(
    frame: pd.DataFrame,
    indices: np.ndarray,
    predictions: np.ndarray,
    fold: Fold,
    candidate: str,
    prepared: PreparedData,
) -> pd.DataFrame:
    """Construct normalized long-form OOS rows for one candidate fold."""
    rows = frame.iloc[indices]
    data: dict[str, Any] = {
        "row_id": rows[prepared.row_id_col].to_numpy(),
        "timestamp": rows[prepared.timestamp_col].to_numpy(),
        "fold": fold.fold,
        "candidate": candidate,
        "prediction": np.asarray(predictions),
        "target": rows[prepared.target_col].to_numpy(),
        "train_start": fold.train_start,
        "train_end": fold.train_end,
        "eval_start": fold.eval_start,
        "eval_end": fold.eval_end,
        "period": rows[prepared.period_col].to_numpy(),
    }
    if prepared.entity_col is not None:
        data["entity"] = rows[prepared.entity_col].to_numpy()
    return pd.DataFrame(data)


def _summary_to_metadata(summary: Any) -> Any:
    """Convert evaluation objects to compact manifest-safe metadata."""
    method = getattr(summary, "to_dict", None)
    return method() if callable(method) else summary


def _in_memory_inference(result: TrainingResult) -> Any:
    """Build the read-only inference view from fitted in-memory components."""

    from ml_engine.inference import InferencePipeline

    return InferencePipeline(result._artifact_payload())


# --------------------------------------------------------------------------- #
# Public training pipeline
# --------------------------------------------------------------------------- #


class TrainingPipeline:
    """Run one explicit, deterministic supervised training configuration."""

    def __init__(self, config: TrainingConfig):
        if not isinstance(config, TrainingConfig):
            raise TypeError("config must be a TrainingConfig")
        self.config = config

    def run(
        self,
        dataset: pd.DataFrame,
        *,
        progress: Callable[[TrainingProgress], None] | None = None,
    ) -> TrainingResult:
        """Validate, evaluate, select, ensemble, and final-refit ``dataset``.

        Every run is tracked in the canonical run store: inside an explicit
        :class:`TrainingRun` progress forwards to that run's sidecar; otherwise an
        implicit best-effort run record is created (see ``run.AutoTrackingContext``).
        A tracking failure is appended to ``TrainingResult.warnings`` and does not
        fail the fit.
        """

        tracker = AutoTrackingContext(progress)
        with tracker as tracked:
            result = self._run(dataset, progress=tracked)
        _attach_tracking_notices(result, tracker.notices)
        return result

    def _run(
        self,
        dataset: pd.DataFrame,
        *,
        progress: Callable[[TrainingProgress], None] | None,
    ) -> TrainingResult:
        """Execute the untracked training body."""

        candidate_count: int | None = None
        fold_count: int | None = None
        total_fits: int | None = None
        completed_fits = 0
        current_candidate: str | None = None
        current_candidate_index: int | None = None
        current_fold_index: int | None = None

        def notify(
            stage: TrainingStage,
            *,
            candidate: str | None = None,
            candidate_index: int | None = None,
            fold_index: int | None = None,
        ) -> None:
            """Emit one exact lifecycle value when observation is requested."""

            nonlocal current_candidate, current_candidate_index, current_fold_index
            if progress is None:
                return
            if candidate is not None:
                current_candidate = candidate
            if candidate_index is not None:
                current_candidate_index = candidate_index
            if fold_index is not None:
                current_fold_index = fold_index
            progress(
                TrainingProgress(
                    stage=stage,
                    task=self.config.task,
                    target=self.config.target_col,
                    feature_count=len(self.config.feature_cols),
                    final_refit=self.config.final_refit,
                    candidate=current_candidate,
                    candidate_index=current_candidate_index,
                    candidate_count=candidate_count,
                    fold_index=current_fold_index,
                    fold_count=fold_count,
                    completed_fits=completed_fits,
                    total_fits=total_fits,
                )
            )

        notify("validation")
        self.config.validate()
        prepared = validate_training_data(dataset, self.config)
        frame = prepared.frame
        candidates = tuple(self.config.candidates)
        names = tuple(candidate.name for candidate in candidates)
        notify("planning")
        planner = (
            build_holdout_plan
            if self.config.split.kind == "chronological_holdout"
            else build_walk_forward_plan
        )
        plan = planner(
            frame,
            self.config.split,
            timestamp_col=prepared.timestamp_col,
            row_id_col=prepared.row_id_col,
            period_col=prepared.period_col,
            target_end_col=prepared.target_end_col,
            training_cutoff=None,
        )
        folds = plan.folds
        if not folds:
            raise ValueError("Split configuration produced no folds")

        candidate_count = len(candidates)
        fold_count = len(folds)
        total_fits = candidate_count * fold_count
        notify("cross_validation")
        oos_parts: list[pd.DataFrame] = []
        fold_models: dict[str, dict[int, Any]] = (
            {candidate.name: {} for candidate in candidates} if self.config.keep_fold_models else {}
        )
        fold_preprocessors: dict[str, dict[int, Any]] = {name: {} for name in fold_models}
        target_observed = frame[prepared.target_col].notna().to_numpy()
        evaluation_retained = target_observed
        if prepared.target_end_col is not None:
            evaluation_retained = target_observed | frame[prepared.target_end_col].isna().to_numpy()
        for candidate_index, candidate in enumerate(candidates, start=1):
            name = candidate.name
            features = _feature_cols(self.config, candidate)
            for fold_index, fold in enumerate(folds, start=1):
                notify(
                    "cross_validation",
                    candidate=name,
                    candidate_index=candidate_index,
                    fold_index=fold_index,
                )
                train_idx = np.asarray(fold.train_indices)
                train_idx = train_idx[target_observed[train_idx]]
                eval_idx = np.asarray(fold.eval_indices)
                eval_idx = eval_idx[evaluation_retained[eval_idx]]
                if len(train_idx) == 0:
                    raise ValueError(
                        f"Candidate {name!r} has no target-observed training rows in a fold"
                    )
                if len(eval_idx) == 0:
                    raise ValueError(
                        f"Candidate {name!r} has no target-observed evaluation rows in a fold"
                    )
                task = candidate.task or self.config.task
                full_fit = fit_full_data(
                    frame.iloc[train_idx],
                    feature_cols=features,
                    target_col=prepared.target_col,
                    candidates=(candidate,),
                    preprocessing=self.config.preprocessing,
                    task=task,
                    random_seed=int(self.config.random_seed),
                    weight_col=self.config.weight_col,
                )
                if self.config.keep_fold_models:
                    fold_models[name][fold.fold] = full_fit.estimators[name]
                    fold_preprocessors[name][fold.fold] = full_fit.preprocessor
                predictions = full_fit.predict(
                    frame.iloc[eval_idx].loc[:, list(features)], candidate=name
                )
                oos_parts.append(_oos_row(frame, eval_idx, predictions, fold, name, prepared))
                completed_fits += 1
                notify(
                    "cross_validation",
                    candidate=name,
                    candidate_index=candidate_index,
                    fold_index=fold_index,
                )
        notify("evaluation")
        candidate_oos = pd.concat(oos_parts, ignore_index=True)
        labeled_candidate_oos = candidate_oos.loc[candidate_oos["target"].notna()]
        summaries = evaluate_candidates(
            labeled_candidate_oos,
            self.config.metrics,
            period_col="period",
            fold_col="fold",
        )
        notify("selection")
        selection = select_candidate(self.config.selection, summaries, candidate_order=names)
        if selection.selected_name is None:
            raise ValueError("No candidate passed selection eligibility gates")
        selected_names = _ensemble_names(self.config.ensemble, selection, names)
        _validate_selected_features(self.config, candidates, selected_names)
        candidates_by_name = {candidate.name: candidate for candidate in candidates}
        selected_tasks = {
            candidates_by_name[name].task or self.config.task for name in selected_names
        }
        if len(selected_tasks) != 1:
            raise ValueError("Selected ensemble candidates must use the same task")

        ensemble_result: EnsembleResult | None = None
        ensemble_oos: pd.DataFrame | None = None
        ensemble_metrics: EvaluationSummary | None = None
        warnings: list[str] = []
        if self.config.ensemble.kind != "none":
            notify("ensemble")
            selected_oos = candidate_oos.loc[candidate_oos["candidate"].isin(selected_names)].copy()
            ensemble_result = fit_ensemble(
                self.config.ensemble,
                selected_oos,
            )
            if len(selected_names) > 1 and ensemble_result.combiner is None:
                fallback_name = (
                    selection.selected_name
                    if selection.selected_name in selected_names
                    else selected_names[0]
                )
                selected_names = (fallback_name,)
            if ensemble_result.fallback_used and ensemble_result.fallback_reason:
                warnings.append(ensemble_result.fallback_reason)
            if ensemble_result.oos_predictions is not None:
                # Ensemble helpers retain row IDs in their pivot order.
                row_ids = np.asarray(ensemble_result.row_ids)
                base_rows = (
                    selected_oos.drop_duplicates("row_id", keep="first")
                    .set_index("row_id")
                    .reindex(row_ids)
                    .reset_index()
                )
                ensemble_oos = base_rows.loc[
                    :, [column for column in base_rows.columns if column != "candidate"]
                ].copy()
                ensemble_oos["prediction"] = ensemble_result.oos_predictions
                ensemble_oos["candidate"] = "ensemble"
                ensemble_oos = ensemble_oos.loc[
                    np.isfinite(ensemble_oos["prediction"].to_numpy())
                ].reset_index(drop=True)
                labeled_ensemble_oos = ensemble_oos.loc[ensemble_oos["target"].notna()]
                ensemble_metrics = evaluate_oos(
                    labeled_ensemble_oos,
                    self.config.metrics,
                    period_col="period",
                    fold_col="fold",
                )

        selected_candidate = candidates_by_name[selected_names[0]]
        selected_features = _feature_cols(self.config, selected_candidate)
        selected_task = selected_candidate.task or self.config.task
        final_preprocessor = None
        final_estimators = None
        transformed_schema: dict[str, Any] = {}
        if self.config.final_refit:
            notify("final_refit")
            final_mask = frame[prepared.target_col].notna()
            if prepared.target_end_col is not None:
                final_mask &= frame[prepared.target_end_col].notna()
            final_rows = frame.loc[final_mask].copy()
            if final_rows.empty:
                raise ValueError("No target-observed rows remain for final refit")
            full_fit = fit_full_data(
                final_rows,
                feature_cols=selected_features,
                target_col=prepared.target_col,
                candidates=tuple(candidates_by_name[name] for name in selected_names),
                preprocessing=self.config.preprocessing,
                task=selected_task,
                random_seed=int(self.config.random_seed),
                weight_col=self.config.weight_col,
            )
            final_preprocessor = full_fit.preprocessor
            final_estimators = full_fit.estimators
            transformed_schema = {"columns": list(final_preprocessor.get_feature_names_out())}

        prediction_transform = self.config.prediction_transform
        if prediction_transform is not None and hasattr(prediction_transform, "fit"):
            raise ValueError(
                "Fittable prediction transforms are not supported because they require "
                "a leakage-safe OOS fitting protocol"
            )

        metadata = {
            "task": self.config.task,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "selected_candidates": list(selected_names),
            "candidate_metrics": {
                name: _summary_to_metadata(summary) for name, summary in summaries.items()
            },
        }
        if warnings:
            metadata["warnings"] = list(warnings)
        result = TrainingResult(
            config=self.config,
            feature_schema={
                "feature_cols": list(selected_features),
                "dtypes": {column: str(frame[column].dtype) for column in selected_features},
                "row_id_col": self.config.row_id_col,
                "timestamp_col": self.config.timestamp_col,
                "entity_col": self.config.entity_col,
            },
            transformed_feature_schema=transformed_schema,
            fold_plan=plan,
            candidate_oos=candidate_oos,
            candidate_metrics=summaries,
            selection_report=selection,
            selected_candidates=selected_names,
            ensemble_oos=ensemble_oos,
            ensemble_metrics=ensemble_metrics,
            _final_preprocessor=final_preprocessor,
            _final_estimators=final_estimators,
            final_ensemble=ensemble_result.combiner if ensemble_result is not None else None,
            prediction_transform=prediction_transform,
            training_cutoff=prepared.training_cutoff,
            data_bounds={
                "start": frame[prepared.timestamp_col].min(),
                "end": frame[prepared.timestamp_col].max(),
            },
            metadata=metadata,
            random_seed=int(self.config.random_seed),
            warnings=tuple(warnings),
            fold_models=fold_models,
            fold_preprocessors=fold_preprocessors,
        )
        if self.config.final_refit:
            result._inference_pipeline = _in_memory_inference(result)
        return result


def _attach_tracking_notices(result: TrainingResult, notices: list[str]) -> None:
    """Copy tracking failures onto the result the caller inspects and saves."""

    if not notices:
        return
    result.warnings = tuple(result.warnings) + tuple(notices)
    metadata = dict(result.metadata)
    recorded = metadata.get("warnings")
    if isinstance(recorded, list):
        metadata["warnings"] = [*recorded, *notices]
    else:
        metadata["warnings"] = list(notices)
    result.metadata = metadata


def _validate_selected_features(
    config: TrainingConfig,
    candidates: tuple[CandidateConfig, ...],
    selected_names: tuple[str, ...],
) -> None:
    """Require one feature schema when v1 persists a single preprocessor."""
    if len(selected_names) < 2:
        return
    by_name = {candidate.name: candidate for candidate in candidates}
    selected_features = {name: _feature_cols(config, by_name[name]) for name in selected_names}
    expected = selected_features[selected_names[0]]
    if any(features != expected for features in selected_features.values()):
        raise ValueError(
            "Multi-model ensembles require identical candidate feature_cols "
            "because v1 persists one preprocessor"
        )


def _ensemble_names(
    config: EnsembleConfig, selection: SelectionReport, declaration_order: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve configured ensemble bases, defaulting to the selected model."""
    if config.kind == "none":
        return (selection.selected_name,) if selection.selected_name is not None else ()
    configured = config.base_models
    if configured:
        values = tuple(configured)
        unknown = [value for value in values if value not in declaration_order]
        if unknown:
            raise ValueError(f"Ensemble references unknown candidates: {unknown}")
        ineligible = [value for value in values if value not in selection.eligible_candidates]
        if ineligible:
            raise ValueError(f"Ensemble references ineligible candidates: {ineligible}")
        return values
    return (selection.selected_name,) if selection.selected_name is not None else ()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

__all__ = ["TrainingPipeline"]
