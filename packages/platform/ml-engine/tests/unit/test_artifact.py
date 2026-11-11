"""Unit tests for versioned, checksum-verified model artifacts.

Usage::

    pytest tests/unit/test_artifact.py

The fixtures use simple serializable dictionaries as fitted objects.  This
keeps the tests focused on the artifact boundary rather than estimator logic.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from ml_engine._artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactSchemaError,
    UntrustedArtifactError,
    load_artifact,
    save_artifact,
)


def _payload() -> ArtifactPayload:
    """Return one compact payload covering every required artifact member."""

    return ArtifactPayload(
        config={"feature_cols": ["feature"], "target_col": "target", "task": "regression"},
        schema={"feature_cols": ["feature"]},
        preprocessor={"kind": "passthrough"},
        models={"linear": {"coefficient": 1.0}},
        ensemble={"kind": "equal_weight"},
        prediction_transform={"kind": "identity"},
        oos_predictions=pd.DataFrame(
            {"row_id": [1, 2], "prediction": [1.0, 2.0], "target": [1.0, 2.0]}
        ),
        metrics={"linear": {"mae": 0.0}},
        selection={"selected_candidates": ["linear"]},
        manifest={},
    )


# --------------------------------------------------------------------------- #
# Save and load behavior
# --------------------------------------------------------------------------- #


def test_round_trip_writes_contract_and_returns_payload(tmp_path: Path) -> None:
    """Round trips preserve JSON values, fitted objects, and OOS evidence."""

    destination = save_artifact(tmp_path / "model-v1", _payload())

    assert destination.is_dir()
    assert {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    } == {
        "manifest.json",
        "config.json",
        "schema.json",
        "preprocessing.joblib",
        "models/linear.joblib",
        "ensemble.joblib",
        "prediction_transform.joblib",
        "oos_predictions.parquet",
        "metrics.json",
        "selection.json",
        "checksums.json",
    }

    loaded = load_artifact(destination, trusted=True)
    assert loaded.config == _payload().config
    assert loaded.schema == _payload().schema
    assert loaded.models == _payload().models
    assert loaded.ensemble == _payload().ensemble
    pd.testing.assert_frame_equal(loaded.oos_predictions, _payload().oos_predictions)
    assert loaded.manifest["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert (
        loaded.manifest["configuration_fingerprint"]
        == hashlib.sha256((destination / "config.json").read_bytes().rstrip(b"\n")).hexdigest()
    )


def test_existing_destination_fails_without_overwrite(tmp_path: Path) -> None:
    """A second save cannot replace an already complete destination."""

    destination = save_artifact(tmp_path / "model-v1", _payload())
    before = (destination / "manifest.json").read_bytes()

    with pytest.raises(FileExistsError):
        save_artifact(destination, _payload())

    assert (destination / "manifest.json").read_bytes() == before
    assert not list(tmp_path.glob(".model-v1.tmp-*"))


# --------------------------------------------------------------------------- #
# Integrity and trust policy
# --------------------------------------------------------------------------- #


def test_checksum_is_verified_before_joblib_deserialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tampered bytes fail before the serialized model is handed to joblib."""

    destination = save_artifact(tmp_path / "model-v1", _payload())
    model_path = destination / "models" / "linear.joblib"
    model_path.write_bytes(model_path.read_bytes() + b"tampered")

    import joblib

    monkeypatch.setattr(joblib, "load", lambda *_args, **_kwargs: pytest.fail("deserialized early"))
    with pytest.raises(ArtifactIntegrityError, match="checksum"):
        load_artifact(destination, trusted=True)


def test_unsupported_schema_fails_before_deserialization(tmp_path: Path) -> None:
    """An unsupported manifest version is rejected before loading joblib files."""

    destination = save_artifact(tmp_path / "model-v1", _payload())
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION + 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ArtifactSchemaError, match="manifest"):
        load_artifact(destination, trusted=True)


def test_default_load_and_explicit_untrusted_mode_fail(tmp_path: Path) -> None:
    """Callers must make a trusted-source decision before executing joblib."""

    destination = save_artifact(tmp_path / "model-v1", _payload())
    with pytest.raises(UntrustedArtifactError, match="(?i)trusted"):
        load_artifact(destination)
    with pytest.raises(UntrustedArtifactError, match="(?i)trusted"):
        load_artifact(destination, trusted=False)
