"""Verify deterministic, OOS-only candidate selection.

Usage::

    pytest tests/unit/training/test_selection.py

The tests use concrete ``EvaluationSummary`` objects because the selector
intentionally consumes the evaluation boundary rather than raw predictions.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ml_engine.training.config import SelectionConfig
from ml_engine.training.evaluation import EvaluationSummary
from ml_engine.training.selection import select_candidate

# --------------------------------------------------------------------------- #
# Test helpers
# --------------------------------------------------------------------------- #


def _config(**overrides: Any) -> SelectionConfig:
    """Build a selection config while keeping tests independent of defaults."""
    values: dict[str, Any] = {
        "primary_metric": "rmse",
        "direction": "minimize",
        "min_coverage": 0.0,
        "min_folds": 0,
        "max_instability": None,
        "max_loss": None,
        "tie_break_fields": (),
    }
    values.update(overrides)
    return SelectionConfig(**values)


def _summary(
    rmse: float | None,
    *,
    coverage: float = 1.0,
    fold_count: int = 0,
    **values: float | None,
) -> EvaluationSummary:
    """Return a compact candidate OOS summary."""
    metrics = {"rmse": rmse, **values}
    return EvaluationSummary(
        metrics=metrics,
        metric_results={},
        n_observations=round(coverage * 100),
        n_rows=100,
        coverage=coverage,
        per_period=pd.DataFrame(),
        per_fold=pd.DataFrame(index=range(fold_count)),
    )


# --------------------------------------------------------------------------- #
# Selection behavior
# --------------------------------------------------------------------------- #


def test_minimization_and_declaration_order_tie_break() -> None:
    """Choose the lowest OOS loss and preserve declaration order on ties."""
    report = select_candidate(
        _config(tie_break_fields=("coverage",)),
        {
            "later": _summary(0.5, coverage=0.95),
            "first": _summary(0.5, coverage=0.80),
            "best": _summary(0.2, coverage=0.40),
        },
        candidate_order=("first", "later", "best"),
    )

    assert report.selected_name == "best"
    tied = select_candidate(
        _config(),
        {"second": _summary(0.5), "first": _summary(0.5)},
        candidate_order=("first", "second"),
    )
    assert tied.selected_name == "first"


def test_maximization_uses_metric_values_and_tie_fields() -> None:
    """Maximization ranks larger primary metrics before configured ties."""
    report = select_candidate(
        _config(primary_metric="correlation", direction="maximize", tie_break_fields=("coverage",)),
        {
            "low": _summary(0.0, correlation=0.8, coverage=0.99),
            "high": _summary(0.0, correlation=0.9, coverage=0.50),
            "tie": _summary(0.0, correlation=0.9, coverage=0.75),
        },
        candidate_order=("low", "high", "tie"),
    )

    assert report.selected_name == "tie"


def test_gates_and_undefined_primary_are_recorded() -> None:
    """Reject failed gates without converting undefined metrics into scores."""
    report = select_candidate(
        _config(
            min_coverage=0.8,
            min_folds=3,
            max_instability=0.2,
            max_loss=0.6,
        ),
        {
            "eligible": _summary(
                0.4,
                coverage=0.9,
                fold_count=4,
                instability=0.1,
                loss=0.5,
            ),
            "low-coverage": _summary(
                0.1,
                coverage=0.5,
                fold_count=4,
                instability=0.1,
                loss=0.1,
            ),
            "undefined": _summary(
                float("nan"),
                coverage=1.0,
                fold_count=4,
                instability=0.1,
                loss=0.1,
            ),
        },
        candidate_order=("eligible", "low-coverage", "undefined"),
    )

    assert report.selected_name == "eligible"
    assert report.eligible_candidates == ("eligible",)
    assert report.ineligible_candidates == ("low-coverage", "undefined")
    low_coverage = report.candidates[1]
    assert not low_coverage.gate_outcomes["min_coverage"].passed
    assert "min_coverage" in low_coverage.reasons
    undefined = report.candidates[2]
    assert not undefined.gate_outcomes["primary_metric_defined"].passed
    assert undefined.comparison_values["rmse"] is None


def test_json_report_retains_structured_evidence() -> None:
    """Retain structured report evidence for serialized artifact metadata."""
    report = select_candidate(
        _config(),
        {"a": _summary(0.2), "b": _summary(0.1)},
        candidate_order=("a", "b"),
    )

    assert report.selected_name == "b"
    payload = report.to_dict()
    assert payload["selected_name"] == "b"
    assert payload["candidates"]["a"]["comparison_values"]["rmse"] == 0.2
