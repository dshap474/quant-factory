"""Exercise the standalone artifact boundary against tampering and races.

Usage::

    pytest tests/integration/test_artifact_security.py

The fixture writes only a local, deliberately tiny trusted artifact.  Tests
then mutate its manifest or serialized payload to prove that validation runs
before deserialization and that failed/duplicate writes cannot replace a
valid destination.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import pytest

from ml_engine._artifact import (
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactSchemaError,
    ArtifactSerializationError,
    UntrustedArtifactError,
    load_artifact,
    save_artifact,
)

# --------------------------------------------------------------------------- #
# Tiny artifact fixture and manifest helpers
# --------------------------------------------------------------------------- #


def _payload() -> ArtifactPayload:
    """Return a serializable payload without invoking a training pipeline."""
    return ArtifactPayload(
        config={"feature_cols": ["feature"], "target_col": "target"},
        schema={"feature_cols": ["feature"]},
        preprocessor={"kind": "passthrough"},
        models={"linear": {"coef": [1.0]}},
        oos_predictions=pd.DataFrame({"row_id": [1], "prediction": [1.0], "target": [1.0]}),
        metrics={"linear": {"mae": 0.0}},
        selection={"selected": ["linear"]},
        manifest={"task": "regression", "selected_model": "linear"},
    )


def _save(path: Path) -> Path:
    """Create one artifact through the production save helper."""
    return save_artifact(path, _payload())


def _rewrite_manifest(path: Path, mutate: Any) -> None:
    """Apply a manifest mutation and refresh its declared checksum."""
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checksums_path = path / "checksums.json"
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    checksums["manifest.json"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Integrity and manifest validation
# --------------------------------------------------------------------------- #


def test_checksum_tamper_is_rejected_before_deserialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never hand a modified joblib file to the deserializer."""
    destination = _save(tmp_path / "model-v1")
    model_file = destination / "models" / "linear.joblib"
    model_file.write_bytes(model_file.read_bytes() + b"tampered")

    def deserialization_must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("joblib.load ran before checksum validation")

    monkeypatch.setattr(joblib, "load", deserialization_must_not_run)
    with pytest.raises(ArtifactIntegrityError, match="(?i)(checksum|integrity|mismatch)"):
        load_artifact(destination, trusted=True)


def test_joblib_replacement_after_initial_verification_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind deserialization to bytes that still match the verified digest."""

    destination = _save(tmp_path / "model-race")
    model_file = destination / "models" / "linear.joblib"

    import ml_engine._artifact_io as artifact_io

    original_verify = artifact_io._verify_files

    def replace_after_verify(root: Path, declared: list[str]) -> dict[str, str]:
        checksums = original_verify(root, declared)
        model_file.write_bytes(model_file.read_bytes() + b"replaced")
        return checksums

    monkeypatch.setattr(artifact_io, "_verify_files", replace_after_verify)
    with pytest.raises(ArtifactIntegrityError, match="checksum"):
        load_artifact(destination, trusted=True)


def test_undeclared_optional_joblib_created_after_verification_is_not_loaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional executable members are selected from the verified declaration only."""

    destination = _save(tmp_path / "model-optional-race")
    optional_file = destination / "ensemble.joblib"

    import ml_engine._artifact_io as artifact_io

    original_verify = artifact_io._verify_files

    def create_after_verify(root: Path, declared: list[str]) -> dict[str, str]:
        checksums = original_verify(root, declared)
        joblib.dump({"unexpected": True}, optional_file)
        return checksums

    monkeypatch.setattr(artifact_io, "_verify_files", create_after_verify)
    loaded = load_artifact(destination, trusted=True)

    assert loaded.ensemble is None


@pytest.mark.parametrize(
    ("manifest_mode", "error_type"),
    (("missing", ArtifactIntegrityError), ("unsupported", ArtifactSchemaError)),
)
def test_missing_or_unsupported_manifest_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_mode: str,
    error_type: type[Exception],
) -> None:
    """Reject malformed manifest metadata before loading serialized state."""
    destination = _save(tmp_path / f"model-{manifest_mode}")
    if manifest_mode == "missing":
        (destination / "manifest.json").unlink()
    else:
        _rewrite_manifest(
            destination,
            lambda manifest: manifest.update({"artifact_schema_version": 999999}),
        )

    def deserialization_must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("joblib.load ran before manifest validation")

    monkeypatch.setattr(joblib, "load", deserialization_must_not_run)
    with pytest.raises(error_type, match="(?i)(manifest|schema)"):
        load_artifact(destination, trusted=True)


# --------------------------------------------------------------------------- #
# Atomic destination semantics
# --------------------------------------------------------------------------- #


def test_existing_destination_is_not_overwritten(
    tmp_path: Path,
) -> None:
    """A second save fails and leaves the first complete artifact untouched."""
    destination = _save(tmp_path / "model-v1")
    before = {
        relative: file.read_bytes()
        for file in destination.rglob("*")
        if file.is_file()
        for relative in [file.relative_to(destination)]
    }

    with pytest.raises(FileExistsError):
        save_artifact(destination, _payload())

    after = {
        relative: file.read_bytes()
        for file in destination.rglob("*")
        if file.is_file()
        for relative in [file.relative_to(destination)]
    }
    assert after == before
    assert not list(destination.parent.glob(f".{destination.name}.*"))


def test_failed_save_removes_temporary_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A serialization failure must not leave an apparently valid destination."""
    destination = tmp_path / "failed-model"

    def fail_dump(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("synthetic serialization failure")

    monkeypatch.setattr(joblib, "dump", fail_dump)
    with pytest.raises(ArtifactSerializationError, match="(?i)serializ"):
        save_artifact(destination, _payload())

    assert not destination.exists()
    assert not list(destination.parent.glob(f".{destination.name}.*"))


# --------------------------------------------------------------------------- #
# Trusted-code warning and documentation contract
# --------------------------------------------------------------------------- #


def test_trusted_artifact_load_requires_explicit_opt_in(
    tmp_path: Path,
) -> None:
    """Loading denies by default and requires explicit trusted opt-in."""
    destination = _save(tmp_path / "trusted-model")

    with pytest.raises(UntrustedArtifactError, match="(?i)trusted"):
        load_artifact(destination)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = load_artifact(destination, trusted=True)
    assert isinstance(loaded, ArtifactPayload)
    assert not caught

    with pytest.raises(UntrustedArtifactError, match="(?i)trusted"):
        load_artifact(destination, trusted=False)


def test_trusted_artifact_warning_is_documented() -> None:
    """Keep the operator-facing warning alongside the loader contract."""
    readme = Path(__file__).parents[2] / "README.md"
    docs = readme.read_text(encoding="utf-8").lower()
    assert "trusted" in docs
    assert "serialized python" in docs
    assert "may execute" in docs

    load_doc = load_artifact.__doc__ or ""
    assert "trusted" in load_doc.lower()
