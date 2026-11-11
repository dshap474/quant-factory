"""Validate caller-owned analysis and search declarations without persistence.

Usage: ``validate_analysis_record(record)``; ``validate_search_evidence(search)``.
Use ``dataclasses.asdict`` for caller-directed serialization; references are opaque.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and immutable declarations
# --------------------------------------------------------------------------- #
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Literal


@dataclass(frozen=True)
class AnalysisRecord:
    """References to one candidate's frozen analysis inputs and existing records.

    A literal ``"unknown"`` reference retains unreconstructed provenance. Values
    are declarations, not proof that referenced data exist or were available.
    """

    candidate_id: str
    revision: str
    frozen_at: datetime
    data_reference: str
    universe_reference: str
    target_reference: str
    input_fingerprint: str
    package_version: str
    code_revision: str
    metric_reference: str
    protocol_reference: str
    partitions_reference: str
    fitting_reference: str
    results_reference: str


@dataclass(frozen=True)
class TrialRecord:
    """One supplied trial, including rejected candidates and failed computations."""

    trial_id: str
    candidate_id: str
    result_reference: str
    status: Literal["completed", "failed", "rejected"]


@dataclass(frozen=True)
class SearchEvidence:
    """A declared search family with complete or explicitly unknown history."""

    search_family_id: str
    completeness: Literal["complete", "unknown"]
    history_reference: str
    holdout_access_reference: str
    trials: tuple[TrialRecord, ...]


# --------------------------------------------------------------------------- #
# Declaration validation
# --------------------------------------------------------------------------- #


def _text(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be nonempty without surrounding whitespace")


def validate_analysis_record(record: AnalysisRecord) -> None:
    """Validate shape, identifiers, and explicit UTC freeze time; perform no I/O."""
    if not isinstance(record, AnalysisRecord):
        raise TypeError("expected AnalysisRecord")
    for field in fields(record):
        if field.name != "frozen_at":
            _text(getattr(record, field.name), field.name)
    if not isinstance(record.frozen_at, datetime):
        raise TypeError("frozen_at must be a datetime")
    if record.frozen_at.tzinfo is None or record.frozen_at.utcoffset() != timedelta(0):
        raise ValueError("frozen_at must be timezone-aware with UTC offset zero")


def validate_search_evidence(search: SearchEvidence) -> None:
    """Validate declared trials; this cannot establish completeness or no access."""
    if not isinstance(search, SearchEvidence):
        raise TypeError("expected SearchEvidence")
    for name in ("search_family_id", "history_reference", "holdout_access_reference"):
        _text(getattr(search, name), name)
    if search.completeness not in ("complete", "unknown"):
        raise ValueError("completeness must be complete or unknown")
    if not isinstance(search.trials, tuple):
        raise TypeError("trials must be a tuple of TrialRecord values")
    if search.completeness == "complete" and search.history_reference == "unknown":
        raise ValueError("complete search history requires a known history reference")
    seen = set()
    for trial in search.trials:
        if not isinstance(trial, TrialRecord):
            raise TypeError("each trial must be a TrialRecord")
        for name in ("trial_id", "candidate_id", "result_reference"):
            _text(getattr(trial, name), name)
        if trial.status not in ("completed", "failed", "rejected"):
            raise ValueError("trial status must be completed, failed, or rejected")
        if trial.trial_id in seen:
            raise ValueError("duplicate trial_id")
        seen.add(trial.trial_id)


__all__ = ["AnalysisRecord", "TrialRecord", "SearchEvidence", "validate_analysis_record", "validate_search_evidence"]
