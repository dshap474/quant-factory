"""Validate evidence declarations without treating them as independent proof.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_evidence.py``.
"""

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from signal_analysis.evidence import (
    AnalysisRecord,
    SearchEvidence,
    TrialRecord,
    validate_analysis_record,
    validate_search_evidence,
)

# --------------------------------------------------------------------------- #
# Analysis records
# --------------------------------------------------------------------------- #


def record():
    return AnalysisRecord(
        candidate_id="candidate-v1",
        revision="revision-1",
        frozen_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        data_reference="existing/snapshot",
        universe_reference="unknown",
        target_reference="target-contract",
        input_fingerprint="sha256:caller-supplied",
        package_version="0.2.0",
        code_revision="caller-revision",
        metric_reference="metrics-and-settings",
        protocol_reference="frozen-thresholds-and-clocks",
        partitions_reference="existing-ml-engine-record",
        fitting_reference="none-required",
        results_reference="caller-owned-dated-results",
    )


def test_record_preserves_unknown_and_is_caller_serializable():
    original = record()
    assert validate_analysis_record(original) is None
    assert asdict(original)["universe_reference"] == "unknown"
    with pytest.raises(FrozenInstanceError):
        original.candidate_id = "changed"


@pytest.mark.parametrize("bad", ["", " candidate", "candidate ", None])
def test_record_requires_trimmed_identifiers(bad):
    with pytest.raises((TypeError, ValueError)):
        validate_analysis_record(replace(record(), candidate_id=bad))


@pytest.mark.parametrize(
    "bad", [datetime(2025, 1, 1), datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=1))), "2025-01-01"]
)
def test_record_requires_explicit_utc_freeze_time(bad):
    with pytest.raises((TypeError, ValueError)):
        validate_analysis_record(replace(record(), frozen_at=bad))


# --------------------------------------------------------------------------- #
# Search history declarations
# --------------------------------------------------------------------------- #


def search():
    return SearchEvidence(
        search_family_id="declared-family",
        completeness="complete",
        history_reference="existing-tracker-history",
        holdout_access_reference="unknown",
        trials=(
            TrialRecord("t1", "v1", "dated-results", "completed"),
            TrialRecord("t2", "v2", "failure-log", "failed"),
            TrialRecord("t3", "v3", "rejection-record", "rejected"),
        ),
    )


def test_search_accepts_declared_unknown_access_without_claiming_no_access():
    declared = search()
    assert validate_search_evidence(declared) is None
    assert asdict(declared)["holdout_access_reference"] == "unknown"
    unknown = replace(declared, completeness="unknown", history_reference="unknown")
    assert validate_search_evidence(unknown) is None


def test_complete_history_requires_reference_and_unique_trials():
    with pytest.raises(ValueError, match="known history"):
        validate_search_evidence(replace(search(), history_reference="unknown"))
    with pytest.raises(ValueError, match="duplicate"):
        validate_search_evidence(replace(search(), trials=(search().trials[0], search().trials[0])))


@pytest.mark.parametrize(
    "updates", [{"completeness": "probably"}, {"trials": []}, {"trials": ("bad",)}, {"search_family_id": " "}]
)
def test_invalid_search_shapes(updates):
    with pytest.raises((TypeError, ValueError)):
        validate_search_evidence(replace(search(), **updates))


@pytest.mark.parametrize("updates", [{"trial_id": " t1"}, {"status": "winner"}, {"result_reference": ""}])
def test_invalid_trial_declarations(updates):
    bad = replace(search().trials[0], **updates)
    with pytest.raises(ValueError):
        validate_search_evidence(replace(search(), trials=(bad,)))
