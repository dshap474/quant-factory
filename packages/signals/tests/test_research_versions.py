"""Tests for signal research-version discovery and research-surface publication.

USAGE:
    uv run pytest packages/signals/tests/test_research_versions.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import json
from pathlib import Path

import polars as pl
import pytest
from signals.research_surface import (
    SurfaceArm,
    load_research_surface,
    load_surface_table,
    publish_research_surface,
)
from signals.research_versions import discover_signal_research_versions

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _write_version(families_root: Path, *, status: str = "supported") -> None:
    version_root = families_root / "family/optimization/v001"
    version_root.mkdir(parents=True)
    (version_root / "VERSION.toml").write_text(
        f'version = 1\nphase = "recorded"\nstatus = "{status}"\n',
        encoding="utf-8",
    )


def _write_attempt(
    db_root: Path,
    run_id: str,
    *,
    not_tested_at: str | None = None,
    extra_json: bool = False,
) -> Path:
    run_root = db_root / "research/signals/family/v001/experiment" / run_id
    run_root.mkdir(parents=True)
    if not_tested_at is not None:
        (run_root / "NOT_TESTED.json").write_text(
            json.dumps(
                {
                    "status": "NOT TESTED",
                    "recorded_at": not_tested_at,
                    "error": "input fingerprint changed",
                }
            ),
            encoding="utf-8",
        )
    else:
        (run_root / "metrics.json").write_text(json.dumps({"verdict": "SUPPORTED"}), encoding="utf-8")
    if extra_json:
        (run_root / "AAA.json").write_text(
            json.dumps({"status": "active", "error": "spoofed"}),
            encoding="utf-8",
        )
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "version": "v001",
                "experiment": "experiment",
            }
        ),
        encoding="utf-8",
    )
    return run_root


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_complete_attempt_uses_run_timestamp_and_ignores_arbitrary_json(tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    families_root = tmp_path / "extensions/lib"
    _write_version(families_root)
    _write_attempt(db_root, "20260101T000000Z-v001-run", extra_json=True)

    versions = discover_signal_research_versions(db_root, families_root)

    assert versions[0]["run_count"] == 1
    assert versions[0]["selected_run_id"] == "20260101T000000Z-v001-run"
    assert versions[0]["latest_run"] == "2026-01-01T00:00:00Z"
    assert versions[0]["lifecycle_status"] == "supported"
    assert versions[0]["invalidation_reason"] is None


def test_later_not_tested_attempt_wins_without_counting_rejections(tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    families_root = tmp_path / "extensions/lib"
    _write_version(families_root, status="not_tested")
    _write_attempt(db_root, "20260101T000000Z-v001-run")
    _write_attempt(
        db_root,
        "20260102T010000Z-v001-run",
        not_tested_at="2026-01-02T01:00:05Z",
        extra_json=True,
    )
    rejection_root = db_root / "research/signals/family/v001/experiment/_rejections/20260902T020000000000Z-duplicate"
    rejection_root.mkdir(parents=True)
    (rejection_root / "NOT_TESTED.json").write_text(
        json.dumps({"status": "NOT TESTED", "recorded_at": "2026-09-02T02:00:00Z"}),
        encoding="utf-8",
    )

    versions = discover_signal_research_versions(db_root, families_root)

    assert versions[0]["run_count"] == 2
    assert versions[0]["selected_run_id"] == "20260102T010000Z-v001-run"
    assert versions[0]["latest_run"] == "2026-01-02T01:00:05Z"
    assert versions[0]["invalidation_reason"] == "input fingerprint changed"


def _publish(db_root: Path, run_id: str, **kwargs: object) -> Path:
    (db_root / "research/signals/family/v001/experiment" / run_id).mkdir(parents=True, exist_ok=True)
    return publish_research_surface(
        db_root,
        signal_family="family",
        memory_version="v001",
        experiment="experiment",
        run_id=run_id,
        title="t",
        summary="s",
        **kwargs,  # type: ignore[arg-type]
    )


def test_summary_only_arm_publishes_without_ic_or_quantiles(tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    quantiles = pl.DataFrame({"target_id": ["h7"], "quantile": [1], "label": ["Q1"], "mean_target": [0.01], "n": [10]})
    arms = [
        SurfaceArm("control", "control", "control", None, None, {"h7_auc": 0.55, "h7_spearman": 0.1}),
        SurfaceArm("candidate", "candidate", "candidate", None, quantiles, {"h7_auc": 0.6}),
    ]
    _publish(db_root, "20260101T000000Z-r01", state="rejected", arms=arms)

    surface = load_research_surface(db_root, "family", "v001")

    assert surface is not None and surface["blocker"] is None
    assert surface["arms"][0]["ic"] is None and surface["arms"][0]["quantiles"] is None
    assert surface["arms"][0]["metrics"]["values"] == {"h7_auc": 0.55, "h7_spearman": 0.1}
    assert surface["arms"][1]["targets"] == ["h7"]
    assert load_surface_table(db_root, "family", "v001", "control", "ic") is None
    assert load_surface_table(db_root, "family", "v001", "candidate", "quantiles") is not None


def test_not_tested_surface_needs_a_blocker_and_no_arms(tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    families_root = tmp_path / "extensions/lib"
    _write_version(families_root, status="not_tested")
    arm = SurfaceArm("control", "control", "control", None, None, {"h7_auc": 0.5})
    with pytest.raises(ValueError, match="blocker"):
        _publish(db_root, "20260101T000000Z-r01", state="not_tested", arms=[])
    with pytest.raises(ValueError, match="no arms"):
        _publish(db_root, "20260101T000000Z-r01", state="not_tested", arms=[arm], blocker="x")
    with pytest.raises(ValueError, match="at least one arm"):
        _publish(db_root, "20260101T000000Z-r01", state="candidate", arms=[])

    _publish(db_root, "20260101T000000Z-r01", state="not_tested", arms=[], blocker="input X missing")

    surface = load_research_surface(db_root, "family", "v001")
    assert surface is not None
    assert (surface["state"], surface["blocker"], surface["arms"]) == ("not_tested", "input X missing", [])
    assert discover_signal_research_versions(db_root, families_root)[0]["surface_state"] == "not_tested"
