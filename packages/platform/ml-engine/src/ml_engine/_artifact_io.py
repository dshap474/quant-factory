"""Filesystem mechanics for complete ``ml-engine`` artifacts.

Usage::

    from ml_engine._artifact_io import load_artifact, save_artifact

This private module writes through a sibling temporary directory, verifies
every declared SHA-256 digest before deserializing joblib objects, and leaves
the public API facade in :mod:`ml_engine._artifact` deliberately small.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and private format dependencies
# --------------------------------------------------------------------------- #
import hashlib
import hmac
import io
import os
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._artifact_format import (
    _CHECKSUMS_FILENAME,
    _MANIFEST_FILENAME,
    _SHA256_RE,
    ArtifactIntegrityError,
    ArtifactPayload,
    ArtifactSerializationError,
    UntrustedArtifactError,
    _json_bytes,
    _manifest_for,
    _model_filename,
    _safe_relative,
    _validate_manifest,
    _validate_runtime_compatibility,
)

# --------------------------------------------------------------------------- #
# File and serialized-object helpers
# --------------------------------------------------------------------------- #


def _write_json(path: Path, value: Any) -> None:
    """Write one canonical JSON file and flush it to the temporary artifact."""

    data = _json_bytes(value)
    with path.open("wb") as handle:
        handle.write(data)
        handle.write(b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: Path) -> Any:
    """Read one JSON file with an artifact-specific error."""

    import json

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError(f"cannot read JSON artifact file {path.name!r}") from exc


def _sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_joblib(path: Path, value: Any) -> None:
    """Serialize one trusted-code object with joblib."""

    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependency is required by package
        raise ArtifactSerializationError("joblib is required to save artifacts") from exc
    try:
        joblib.dump(value, path)
    except Exception as exc:  # joblib exposes estimator-specific exceptions
        raise ArtifactSerializationError(f"serialization failed for {path.name!r}") from exc


def _verified_bytes(path: Path, expected: str) -> bytes:
    """Read one regular file without following a final symlink and re-hash its bytes."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise ArtifactIntegrityError(f"cannot safely read artifact file {path.name!r}") from exc
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected):
        raise ArtifactIntegrityError(f"checksum mismatch for {path.name!r}")
    return data


def _read_joblib(path: Path, expected: str) -> Any:
    """Deserialize freshly verified bytes from one declared trusted-code member."""

    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependency is required by package
        raise ArtifactSerializationError("joblib is required to load artifacts") from exc
    try:
        return joblib.load(io.BytesIO(_verified_bytes(path, expected)))
    except ArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ArtifactIntegrityError(f"cannot deserialize {path.name!r}") from exc


def _write_oos(path: Path, value: Any) -> None:
    """Write the OOS evidence table as parquet."""

    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - dependency is required by package
        raise ArtifactSerializationError("pandas is required to save OOS predictions") from exc
    frame = pd.DataFrame() if value is None else value
    if not isinstance(frame, pd.DataFrame):
        raise ArtifactSerializationError("oos_predictions must be a pandas.DataFrame or None")
    try:
        frame.to_parquet(path, index=False)
    except Exception as exc:
        raise ArtifactSerializationError("cannot serialize OOS predictions as parquet") from exc


def _read_oos(path: Path) -> Any:
    """Read the OOS evidence table after integrity verification."""

    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - dependency is required by package
        raise ArtifactSerializationError("pandas is required to load OOS predictions") from exc
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        raise ArtifactIntegrityError("cannot read OOS predictions parquet") from exc


def _actual_files(root: Path) -> set[str]:
    """Return all regular files below an artifact directory."""

    actual: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise ArtifactIntegrityError(f"artifact contains symlink {candidate.name!r}")
        if candidate.is_file():
            actual.add(candidate.relative_to(root).as_posix())
        elif not candidate.is_dir():
            raise ArtifactIntegrityError(f"artifact contains unsupported entry {candidate.name!r}")
    return actual


def _verify_files(root: Path, declared: list[str]) -> dict[str, str]:
    """Verify every declared file and return its immutable expected digest map."""

    declared_set = set(declared)
    actual = _actual_files(root)
    if actual != declared_set:
        missing = sorted(declared_set - actual)
        undeclared = sorted(actual - declared_set)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if undeclared:
            details.append(f"undeclared={undeclared}")
        raise ArtifactIntegrityError(
            "artifact file set does not match manifest (" + ", ".join(details) + ")"
        )

    checksums = _read_json(root / _CHECKSUMS_FILENAME)
    if not isinstance(checksums, Mapping):
        raise ArtifactIntegrityError("checksums.json must be a JSON object")
    checksum_map: dict[str, str] = {}
    for raw_path, digest in checksums.items():
        path = _safe_relative(raw_path)
        if path == _CHECKSUMS_FILENAME or path not in declared_set:
            raise ArtifactIntegrityError(f"checksum declares unknown file {path!r}")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ArtifactIntegrityError(f"invalid SHA-256 checksum for {path!r}")
        checksum_map[path] = digest
    expected_paths = declared_set - {_CHECKSUMS_FILENAME}
    if set(checksum_map) != expected_paths:
        missing = sorted(expected_paths - set(checksum_map))
        extra = sorted(set(checksum_map) - expected_paths)
        raise ArtifactIntegrityError(
            f"checksum file set mismatch (missing={missing}, extra={extra})"
        )
    for relative, expected in checksum_map.items():
        actual_digest = _sha256(root / relative)
        if not hmac.compare_digest(actual_digest, expected):
            raise ArtifactIntegrityError(f"checksum mismatch for {relative!r}")
    return checksum_map


# --------------------------------------------------------------------------- #
# Public save/load implementation consumed by the facade
# --------------------------------------------------------------------------- #


def save_artifact(path: str | os.PathLike[str], payload: ArtifactPayload) -> Path:
    """Atomically save one complete versioned artifact directory.

    The destination must not already exist.  A failed write removes its sibling
    temporary directory and never leaves a partially valid destination.
    """

    if not isinstance(payload, ArtifactPayload):
        raise TypeError("payload must be an ArtifactPayload")
    artifact = payload
    destination = Path(path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"artifact destination already exists: {destination}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=str(parent)))
    try:
        (temporary / "models").mkdir()

        model_paths: dict[str, str] = {}
        for name, model in artifact.models.items():
            relative = _model_filename(name)
            model_paths[name] = relative
            _write_joblib(temporary / relative, model)

        _write_json(temporary / "config.json", artifact.config)
        _write_json(temporary / "schema.json", artifact.schema)
        _write_joblib(temporary / "preprocessing.joblib", artifact.preprocessor)
        if artifact.ensemble is not None:
            _write_joblib(temporary / "ensemble.joblib", artifact.ensemble)
        if artifact.prediction_transform is not None:
            _write_joblib(temporary / "prediction_transform.joblib", artifact.prediction_transform)
        _write_oos(temporary / "oos_predictions.parquet", artifact.oos_predictions)
        _write_json(temporary / "metrics.json", artifact.metrics)
        _write_json(temporary / "selection.json", artifact.selection)

        artifact_paths = [
            _MANIFEST_FILENAME,
            "config.json",
            "schema.json",
            "preprocessing.joblib",
            *sorted(model_paths.values()),
        ]
        if artifact.ensemble is not None:
            artifact_paths.append("ensemble.joblib")
        if artifact.prediction_transform is not None:
            artifact_paths.append("prediction_transform.joblib")
        artifact_paths.extend(
            ["oos_predictions.parquet", "metrics.json", "selection.json", _CHECKSUMS_FILENAME]
        )
        artifact_paths = sorted(artifact_paths)
        manifest = _manifest_for(artifact, artifact_paths, model_paths)
        _write_json(temporary / _MANIFEST_FILENAME, manifest)

        checksums = {
            relative: _sha256(temporary / relative)
            for relative in artifact_paths
            if relative != _CHECKSUMS_FILENAME
        }
        _write_json(temporary / _CHECKSUMS_FILENAME, checksums)

        # The temporary directory is a sibling, so rename is one filesystem
        # operation and readers never observe a partially populated artifact.
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"artifact destination already exists: {destination}")
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def load_artifact(path: str | os.PathLike[str], *, trusted: bool = False) -> ArtifactPayload:
    """Verify and load a complete artifact directory.

    Joblib may execute serialized Python during loading.  The default
    Callers must pass ``trusted=True`` for an explicit trusted-source decision.
    """

    if not isinstance(trusted, bool):
        raise TypeError("trusted must be a bool")
    if not trusted:
        raise UntrustedArtifactError(
            "InferencePipeline.load() may execute serialized Python; "
            "load artifacts only from trusted sources"
        )
    root = Path(path)
    if not root.is_dir() or root.is_symlink():
        raise ArtifactIntegrityError(f"artifact directory does not exist: {root}")
    manifest = _read_json(root / _MANIFEST_FILENAME)
    declared, model_paths = _validate_manifest(manifest)
    _validate_runtime_compatibility(manifest)
    checksums = _verify_files(root, declared)

    # No executable object is loaded before all manifest and checksum checks
    # above have passed.
    config = _read_json(root / "config.json")
    schema = _read_json(root / "schema.json")
    metrics = _read_json(root / "metrics.json") or {}
    selection = _read_json(root / "selection.json") or {}
    models = {
        name: _read_joblib(root / relative, checksums[relative])
        for name, relative in sorted(model_paths.items())
    }
    preprocessor = _read_joblib(root / "preprocessing.joblib", checksums["preprocessing.joblib"])
    declared_set = set(declared)
    ensemble = (
        _read_joblib(root / "ensemble.joblib", checksums["ensemble.joblib"])
        if "ensemble.joblib" in declared_set
        else None
    )
    prediction_transform = (
        _read_joblib(
            root / "prediction_transform.joblib",
            checksums["prediction_transform.joblib"],
        )
        if "prediction_transform.joblib" in declared_set
        else None
    )
    oos_predictions = _read_oos(root / "oos_predictions.parquet")
    return ArtifactPayload(
        config=config,
        schema=schema,
        preprocessor=preprocessor,
        models=models,
        ensemble=ensemble,
        prediction_transform=prediction_transform,
        oos_predictions=oos_predictions,
        metrics=metrics,
        selection=selection,
        manifest=dict(manifest),
    )
