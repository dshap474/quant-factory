"""Select candidates from out-of-sample evaluation summaries.

Usage::

    report = select_candidate(config.selection, candidate_summaries, candidate_names)
    selected_name = report.selected_name

Selection is deliberately a small, deterministic decision step.  It consumes
only :class:`EvaluationSummary` values produced from row-aligned OOS data; the
final refit and any in-sample estimator statistics are outside this module.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from numbers import Real
from typing import Literal

import pandas as pd

from .config import SelectionConfig
from .evaluation import EvaluationSummary

# --------------------------------------------------------------------------- #
# Public report types
# --------------------------------------------------------------------------- #

Scalar = float | int | None
Direction = Literal["maximize", "minimize"]


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Result of one eligibility gate."""

    passed: bool
    value: Scalar
    threshold: Scalar


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """Selection evidence retained for one declared candidate."""

    name: str
    eligible: bool
    gate_outcomes: Mapping[str, GateOutcome] = field(default_factory=dict)
    comparison_values: Mapping[str, Scalar] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectionReport:
    """Complete, declaration-ordered selection evidence."""

    primary_metric: str
    direction: Direction
    candidates: tuple[CandidateSelection, ...]
    selected_name: str | None

    @property
    def eligible_candidates(self) -> tuple[str, ...]:
        """Names passing every configured gate."""
        return tuple(item.name for item in self.candidates if item.eligible)

    @property
    def ineligible_candidates(self) -> tuple[str, ...]:
        """Names rejected by at least one configured gate."""
        return tuple(item.name for item in self.candidates if not item.eligible)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly structured report."""
        return {
            "primary_metric": self.primary_metric,
            "direction": self.direction,
            "selected_name": self.selected_name,
            "eligible_candidates": list(self.eligible_candidates),
            "ineligible_candidates": list(self.ineligible_candidates),
            "candidates": {
                item.name: {
                    "eligible": item.eligible,
                    "gate_outcomes": {
                        name: {
                            "passed": gate.passed,
                            "value": gate.value,
                            "threshold": gate.threshold,
                        }
                        for name, gate in item.gate_outcomes.items()
                    },
                    "comparison_values": dict(item.comparison_values),
                    "reasons": list(item.reasons),
                }
                for item in self.candidates
            },
        }


# --------------------------------------------------------------------------- #
# OOS summary and ordering helpers
# --------------------------------------------------------------------------- #

_MAXIMIZE_TIE_FIELDS = {"coverage", "n_folds", "n_observations"}


def _finite(value: object) -> float | None:
    """Normalize metric values while preserving undefined values as ``None``."""
    if value is None or isinstance(value, bool):
        return None
    defined = getattr(value, "defined", True)
    if defined is False:
        return None
    value = getattr(value, "value", value)
    if not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _metric(summary: EvaluationSummary, *names: str) -> float | None:
    """Read the first defined scalar among summary metric names."""
    for name in names:
        if name in summary.metrics:
            value = _finite(summary.metrics[name])
            if value is not None:
                return value
    return None


def _summary_value(summary: EvaluationSummary | None, name: str) -> float | None:
    """Read a comparison field from summary metadata or metric values."""
    if summary is None:
        return None
    if name == "coverage":
        return _finite(summary.coverage)
    if name == "n_folds":
        return _finite(summary.n_folds)
    if name == "n_observations":
        return _finite(summary.n_observations)
    return _metric(summary, name)


def _tie_field(field: str, primary_direction: Direction) -> tuple[str, Direction]:
    """Return a tie-break metric and its natural comparison direction."""
    return field, "maximize" if field in _MAXIMIZE_TIE_FIELDS else primary_direction


def _order_key(value: Scalar, direction: Direction) -> tuple[int, float]:
    """Sort defined values before undefined values in a deterministic direction."""
    if value is None:
        return 1, 0.0
    return 0, -float(value) if direction == "maximize" else float(value)


# --------------------------------------------------------------------------- #
# Public selection entry points
# --------------------------------------------------------------------------- #


def select_candidate(
    config: SelectionConfig,
    summaries: Mapping[str, EvaluationSummary],
    candidate_order: Sequence[str] | None = None,
) -> SelectionReport:
    """Select one candidate from OOS summaries only.

    Candidates are ranked by the primary metric, then each configured
    tie-break field, then declaration order.  Undefined primary metrics fail
    the candidate's eligibility gate; undefined tie-break values sort after
    defined values but do not make an otherwise eligible candidate ineligible.
    """
    primary_metric = str(config.primary_metric)
    direction = config.direction
    names = [str(name) for name in (candidate_order or tuple(summaries))]
    if candidate_order is not None:
        names.extend(str(name) for name in summaries if str(name) not in names)
    if len(names) != len(set(names)):
        raise ValueError("Candidate declaration order must contain unique names")

    tie_fields = [_tie_field(field, direction) for field in (config.tie_break_fields or ())]
    minimum_coverage = 0.0 if config.min_coverage is None else float(config.min_coverage)
    minimum_folds = 0 if config.min_folds is None else int(config.min_folds)
    maximum_instability = config.max_instability
    maximum_loss = config.max_loss
    records: list[CandidateSelection] = []
    ranked: list[tuple[tuple[tuple[int, float], ...], int, str]] = []

    for declaration_index, name in enumerate(names):
        summary = summaries.get(name)
        primary_value = _metric(summary, primary_metric) if summary is not None else None
        coverage = summary.coverage if summary is not None else None
        folds = summary.n_folds if summary is not None else None
        instability = (
            _metric(summary, "instability", "stability", "dispersion", "std") if summary else None
        )
        if (
            instability is None
            and summary is not None
            and primary_metric in summary.per_fold.columns
        ):
            fold_values = pd.to_numeric(summary.per_fold[primary_metric], errors="coerce").dropna()
            if not fold_values.empty:
                instability = float(fold_values.std(ddof=0))
        loss = _metric(summary, "loss") if summary else None

        gates = {
            "primary_metric_defined": GateOutcome(primary_value is not None, primary_value, None),
            "min_coverage": GateOutcome(
                minimum_coverage <= 0 or coverage is not None and coverage >= minimum_coverage,
                coverage,
                minimum_coverage,
            ),
            "min_folds": GateOutcome(
                minimum_folds <= 0 or folds is not None and folds >= minimum_folds,
                folds,
                minimum_folds,
            ),
            "max_instability": GateOutcome(
                maximum_instability is None
                or instability is not None
                and instability <= float(maximum_instability),
                instability,
                maximum_instability,
            ),
            "max_loss": GateOutcome(
                maximum_loss is None or loss is not None and loss <= float(maximum_loss),
                loss,
                maximum_loss,
            ),
        }
        comparison_values: dict[str, Scalar] = {primary_metric: primary_value}
        for field_name, _field_direction in tie_fields:
            comparison_values[field_name] = _summary_value(summary, field_name)
        reasons = tuple(name for name, gate in gates.items() if not gate.passed)
        record = CandidateSelection(name, not reasons, gates, comparison_values, reasons)
        records.append(record)
        if record.eligible:
            values = [_order_key(primary_value, direction)]
            values.extend(
                _order_key(comparison_values[field_name], field_direction)
                for field_name, field_direction in tie_fields
            )
            ranked.append((tuple(values), declaration_index, name))

    selected_name = min(ranked)[2] if ranked else None
    return SelectionReport(primary_metric, direction, tuple(records), selected_name)


# --------------------------------------------------------------------------- #
# Module export inventory
# --------------------------------------------------------------------------- #

__all__ = [
    "CandidateSelection",
    "GateOutcome",
    "SelectionReport",
    "select_candidate",
]
