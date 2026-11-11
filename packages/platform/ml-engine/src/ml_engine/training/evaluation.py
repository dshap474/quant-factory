"""Leakage-safe evaluation of row-aligned out-of-sample predictions.

Only an OOS table is accepted.  It must contain ``prediction`` and ``target``
columns and may contain ``period``/``timestamp``, ``fold``, and ``candidate``.

Usage::

    result = evaluate_oos(oos_rows, metrics=("mae", "pearson"))
    result.metrics["mae"]
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ._evaluation_metrics import (
    MetricResult,
    aggregate_group_metric,
    compute_base,
    group_frame,
    metric_spec,
    parse_summary_name,
    valid_rows,
)

# --------------------------------------------------------------------------- #
# Public result type
# --------------------------------------------------------------------------- #


@dataclass
class EvaluationSummary:
    """Metrics and grouped stability summaries for one candidate's OOS rows."""

    metrics: dict[str, float | None]
    metric_results: dict[str, MetricResult]
    n_observations: int
    n_rows: int
    coverage: float
    per_period: pd.DataFrame
    per_fold: pd.DataFrame
    candidate: str | None = None

    @property
    def n_periods(self) -> int:
        """Number of periods represented in the OOS table."""

        return len(self.per_period)

    @property
    def n_folds(self) -> int:
        """Number of folds represented in the OOS table."""

        return len(self.per_fold)

    def to_dict(self) -> dict[str, Any]:
        """Return scalar metrics and counts in a JSON-friendly structure."""

        return {
            "candidate": self.candidate,
            "metrics": dict(self.metrics),
            "n_observations": self.n_observations,
            "n_rows": self.n_rows,
            "coverage": self.coverage,
            "n_periods": self.n_periods,
            "n_folds": self.n_folds,
        }


# --------------------------------------------------------------------------- #
# Input helpers
# --------------------------------------------------------------------------- #


def _metric_iterable(metrics: Iterable[Any] | Any | None) -> Iterable[Any]:
    """Normalize one metric config/string and ordered collections."""

    if metrics is None:
        return ("rmse",)
    if isinstance(metrics, (str, bytes, Mapping)) or hasattr(metrics, "name"):
        return (metrics,)
    return metrics


def _candidate_rows(
    predictions: pd.DataFrame, candidate: str | None
) -> tuple[pd.DataFrame, str | None]:
    if "candidate" not in predictions.columns:
        return predictions.copy(), candidate
    frame = predictions.copy()
    candidates = frame["candidate"].dropna().unique()
    if candidate is not None:
        frame = frame.loc[frame["candidate"] == candidate].copy()
    elif len(candidates) > 1:
        raise ValueError(
            "evaluate_oos received multiple candidates; use evaluate_candidates or candidate="
        )
    elif len(candidates) == 1:
        candidate = str(candidates[0])
    return frame, candidate


# --------------------------------------------------------------------------- #
# Public evaluation entry points
# --------------------------------------------------------------------------- #


def evaluate_oos(
    predictions: pd.DataFrame,
    metrics: Iterable[Any] | None = None,
    *,
    period_col: str | None = None,
    fold_col: str | None = "fold",
    candidate: str | None = None,
) -> EvaluationSummary:
    """Evaluate configured metrics using only row-aligned OOS predictions.

    Missing targets/predictions are excluded from observations and lower
    ``coverage``.  Undefined metrics remain ``None`` with a detailed
    :class:`MetricResult`; they are never replaced by zero.
    """

    if not isinstance(predictions, pd.DataFrame):
        raise TypeError("OOS predictions must be a pandas DataFrame")
    selected, candidate = _candidate_rows(predictions, candidate)
    input_rows = len(selected)
    rows, prediction = valid_rows(selected)
    configs = [metric_spec(item) for item in _metric_iterable(metrics)]

    period = period_col
    if period is None:
        period = next(
            (
                str(options["period_col"])
                for _, _, _, options in configs
                if options.get("period_col")
            ),
            None,
        )
    if period is not None and period not in rows.columns:
        raise ValueError(f"configured period column {period!r} is missing from OOS predictions")
    if period is None:
        period = (
            "period"
            if "period" in rows.columns
            else ("timestamp" if "timestamp" in rows.columns else None)
        )

    configured_fold = next(
        (str(options["fold_col"]) for _, _, _, options in configs if options.get("fold_col")),
        fold_col,
    )
    fold = (
        configured_fold if configured_fold is not None and configured_fold in rows.columns else None
    )

    base_names: set[str] = set()
    for requested, canonical, _, options in configs:
        parsed = parse_summary_name(requested, options)
        base_names.add(parsed[1] if parsed is not None else canonical)
    period_frame = group_frame(rows, prediction, period, base_names)
    fold_frame = group_frame(rows, prediction, fold, base_names)

    details: dict[str, MetricResult] = {}
    for requested, canonical, direction, options in configs:
        minimum = int(options["min_observations"])
        parsed = parse_summary_name(requested, options)
        if parsed is None:
            details[requested] = compute_base(
                canonical,
                rows,
                prediction,
                direction,
                minimum,
                metric_name=requested,
                custom=options.get("callable"),
            )
            continue
        scope, base, statistic = parsed
        groups = period_frame if scope == "period" else fold_frame
        details[requested] = aggregate_group_metric(
            requested, base, statistic, groups, len(rows), direction, minimum
        )

    observations = max((item.n_observations for item in details.values()), default=len(rows))
    coverage = observations / input_rows if input_rows else 0.0
    return EvaluationSummary(
        metrics={name: item.value for name, item in details.items()},
        metric_results=details,
        n_observations=observations,
        n_rows=input_rows,
        coverage=float(coverage),
        per_period=period_frame,
        per_fold=fold_frame,
        candidate=candidate,
    )


def evaluate_candidates(
    predictions: pd.DataFrame,
    metrics: Iterable[Any] | None = None,
    *,
    period_col: str | None = None,
    fold_col: str | None = "fold",
) -> dict[str, EvaluationSummary]:
    """Evaluate every candidate in a long-form OOS prediction table."""

    if not isinstance(predictions, pd.DataFrame) or "candidate" not in predictions.columns:
        raise ValueError("candidate OOS evaluation requires a candidate column")
    metric_list = tuple(_metric_iterable(metrics))
    return {
        str(name): evaluate_oos(group, metric_list, period_col=period_col, fold_col=fold_col)
        for name, group in predictions.groupby("candidate", sort=False, dropna=False)
    }


__all__ = [
    "EvaluationSummary",
    "MetricResult",
    "evaluate_candidates",
    "evaluate_oos",
]
