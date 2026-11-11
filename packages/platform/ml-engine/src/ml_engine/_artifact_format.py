"""Typed values and deterministic metadata for ``ml-engine`` artifacts.

Usage::

    from ml_engine._artifact_format import ArtifactPayload

This module contains no filesystem writes or serialized-object loads.  The
public save/load functions live in :mod:`ml_engine._artifact_io` and are
re-exported by :mod:`ml_engine._artifact`.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and format constants
# --------------------------------------------------------------------------- #
import dataclasses
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final, TypeAlias

ARTIFACT_SCHEMA_VERSION: Final[int] = 1
"""Version of the on-disk artifact schema supported by this package."""

_CHECKSUMS_FILENAME: Final[str] = "checksums.json"
_MANIFEST_FILENAME: Final[str] = "manifest.json"
_REQUIRED_FILES: Final[frozenset[str]] = frozenset(
    {
        _MANIFEST_FILENAME,
        "config.json",
        "schema.json",
        "preprocessing.joblib",
        "oos_predictions.parquet",
        "metrics.json",
        "selection.json",
        _CHECKSUMS_FILENAME,
    }
)
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_MODEL_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[^/\\]+$")
_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^(\d+)(?:\.\d+)?")

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


# --------------------------------------------------------------------------- #
# Errors and typed payload
# --------------------------------------------------------------------------- #


class ArtifactError(RuntimeError):
    """Base class for malformed, incompatible, or unsafe artifacts."""


class ArtifactSchemaError(ArtifactError):
    """Raised when the artifact schema is missing or unsupported."""


class ArtifactCompatibilityError(ArtifactError):
    """Raised when an artifact cannot be used by this runtime."""


class ArtifactIntegrityError(ArtifactError):
    """Raised when files are missing, undeclared, or fail checksum validation."""


class ArtifactSerializationError(ArtifactError):
    """Raised when a payload cannot be represented by the artifact format."""


class UntrustedArtifactError(ArtifactError):
    """Raised when loading serialized Python without a trust decision."""


class TrustedArtifactWarning(UserWarning):
    """Warn that loading an artifact may execute serialized Python code."""


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    """The generic, fitted objects and audit data stored in one artifact."""

    config: Mapping[str, Any]
    schema: Mapping[str, Any]
    preprocessor: Any
    models: Mapping[str, Any]
    ensemble: Any | None = None
    prediction_transform: Any | None = None
    oos_predictions: Any | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    selection: Mapping[str, Any] = field(default_factory=dict)
    manifest: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Deterministic JSON and payload helpers
# --------------------------------------------------------------------------- #


def _jsonable(value: Any) -> JSONValue:
    """Convert a config-like value to deterministic JSON data."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    for method_name in ("to_dict", "to_mapping"):
        method = getattr(value, method_name, None)
        if callable(method):
            return _jsonable(method())
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            result[str(key)] = _jsonable(item)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        converted = [_jsonable(item) for item in value]
        if isinstance(value, (set, frozenset)):
            converted.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return converted
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _jsonable(item_method())
        except (TypeError, ValueError):
            pass
    list_method = getattr(value, "tolist", None)
    if callable(list_method):
        try:
            return _jsonable(list_method())
        except (TypeError, ValueError):
            pass
    get_params = getattr(value, "get_params", None)
    if callable(get_params):
        return {
            "class": f"{type(value).__module__}.{type(value).__qualname__}",
            "params": _jsonable(get_params(deep=False)),
        }
    if callable(value):
        module = getattr(value, "__module__", type(value).__module__)
        name = getattr(value, "__qualname__", type(value).__qualname__)
        return {"callable": f"{module}.{name}"}
    raise ArtifactSerializationError(
        f"value of type {type(value).__name__} is not JSON serializable"
    )


def _json_bytes(value: Any) -> bytes:
    """Encode a JSON-compatible value with stable formatting."""

    try:
        return json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ArtifactSerializationError):
            raise
        raise ArtifactSerializationError("value cannot be encoded as JSON") from exc


def _package_version() -> str:
    """Resolve the installed package version without importing the root module."""

    try:
        return importlib.metadata.version("ml-engine")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0"


def _dependency_versions() -> dict[str, str]:
    """Collect available estimator/runtime dependency versions."""

    versions: dict[str, str] = {}
    for distribution in (
        "scikit-learn",
        "joblib",
        "numpy",
        "pandas",
        "pyarrow",
        "lightgbm",
        "xgboost",
    ):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def _model_filename(name: str) -> str:
    """Validate a candidate name before using it as a relative filename."""

    if not isinstance(name, str) or not name or not _MODEL_NAME_RE.fullmatch(name):
        raise ArtifactSerializationError(
            f"model name {name!r} must be a non-empty filename component"
        )
    if name in {".", ".."}:
        raise ArtifactSerializationError(f"model name {name!r} is not safe")
    return f"models/{name}.joblib"


def _safe_relative(path: str) -> str:
    """Validate and normalize a declared artifact-relative path."""

    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise ArtifactIntegrityError(f"invalid declared artifact path {path!r}")
    candidate = Path(path)
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ArtifactIntegrityError(f"invalid declared artifact path {path!r}")
    normalized = candidate.as_posix()
    if normalized != path:
        raise ArtifactIntegrityError(f"invalid declared artifact path {path!r}")
    return normalized


# --------------------------------------------------------------------------- #
# Manifest and compatibility validation
# --------------------------------------------------------------------------- #


def _manifest_for(
    payload: ArtifactPayload,
    artifact_paths: Sequence[str],
    model_paths: Mapping[str, str],
) -> dict[str, JSONValue]:
    """Build the complete manifest while preserving caller metadata."""

    metadata = _jsonable(payload.manifest or {})
    if not isinstance(metadata, dict):
        raise ArtifactSerializationError("manifest metadata must be a mapping")
    config_bytes = _json_bytes(payload.config)
    schema = _jsonable(payload.schema)
    config = _jsonable(payload.config)
    selection = _jsonable(payload.selection)
    if not isinstance(schema, dict):
        raise ArtifactSerializationError("schema must be a mapping")
    if not isinstance(config, dict):
        raise ArtifactSerializationError("config must be a mapping")
    if not isinstance(selection, dict):
        raise ArtifactSerializationError("selection must be a mapping")
    required_inputs = schema.get("feature_cols")
    if not isinstance(required_inputs, list):
        raise ArtifactSerializationError("schema feature_cols must be an ordered list")

    metadata.setdefault("artifact_schema_version", ARTIFACT_SCHEMA_VERSION)
    if metadata["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactSchemaError(
            "manifest metadata requests unsupported artifact schema version "
            f"{metadata['artifact_schema_version']}"
        )
    metadata.setdefault("ml_engine_version", _package_version())
    metadata.setdefault("created_at", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    metadata.setdefault("task", config.get("task", "regression"))
    metadata.setdefault("selected_candidates", selection.get("selected_candidates", []))
    metadata.setdefault("required_inputs", required_inputs)
    metadata.setdefault("python_version", platform.python_version())
    metadata.setdefault("estimator_library_versions", _dependency_versions())
    metadata.setdefault("configuration_fingerprint", hashlib.sha256(config_bytes).hexdigest())
    metadata["artifact_paths"] = list(artifact_paths)
    metadata["model_paths"] = dict(model_paths)
    return metadata


def _validate_manifest(manifest: Any) -> tuple[list[str], dict[str, str]]:
    """Validate manifest metadata and return declared files/model paths."""

    if not isinstance(manifest, Mapping):
        raise ArtifactSchemaError("manifest must be a JSON object")
    version = manifest.get("artifact_schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ArtifactSchemaError("manifest has no integer artifact_schema_version")
    if version != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactSchemaError(
            f"manifest uses unsupported artifact schema version {version}; "
            f"supported version is {ARTIFACT_SCHEMA_VERSION}"
        )
    declared_raw = manifest.get("artifact_paths")
    if not isinstance(declared_raw, list):
        raise ArtifactSchemaError("manifest artifact_paths must be a list")
    declared = [_safe_relative(path) for path in declared_raw]
    if len(set(declared)) != len(declared):
        raise ArtifactSchemaError("manifest artifact_paths contains duplicates")
    model_paths_raw = manifest.get("model_paths", {})
    if not isinstance(model_paths_raw, Mapping):
        raise ArtifactSchemaError("manifest model_paths must be a mapping")
    model_paths: dict[str, str] = {}
    for name, path in model_paths_raw.items():
        if not isinstance(name, str) or not isinstance(path, str):
            raise ArtifactSchemaError("manifest model_paths must contain strings")
        model_path = _safe_relative(path)
        try:
            expected_model_path = _model_filename(name)
        except ArtifactSerializationError as exc:
            raise ArtifactSchemaError(f"manifest has invalid model name {name!r}") from exc
        if model_path != expected_model_path:
            raise ArtifactIntegrityError(
                f"manifest model path for {name!r} is not its canonical filename"
            )
        model_paths[name] = model_path
    missing = _REQUIRED_FILES - set(declared)
    if missing:
        raise ArtifactIntegrityError(f"manifest omits required files: {sorted(missing)}")
    model_file_set = {
        path for path in declared if path.startswith("models/") and path.endswith(".joblib")
    }
    if set(model_paths.values()) != model_file_set:
        raise ArtifactIntegrityError("manifest model_paths does not match declared model files")
    return declared, model_paths


def _validate_runtime_compatibility(manifest: Mapping[str, Any]) -> None:
    """Reject clearly incompatible runtime versions before deserialization."""

    artifact_python = manifest.get("python_version")
    if isinstance(artifact_python, str):
        match = _VERSION_RE.match(artifact_python)
        if match and int(match.group(1)) != sys.version_info.major:
            raise ArtifactCompatibilityError(
                "artifact was created by a different Python major version; "
                "cross-major portability is not supported"
            )
    artifact_engine = manifest.get("ml_engine_version")
    current_engine = _package_version()
    artifact_engine_match = (
        _VERSION_RE.match(artifact_engine) if isinstance(artifact_engine, str) else None
    )
    current_engine_match = _VERSION_RE.match(current_engine)
    if (
        artifact_engine_match is not None
        and current_engine_match is not None
        and int(artifact_engine_match.group(1)) != int(current_engine_match.group(1))
    ):
        raise ArtifactCompatibilityError(
            f"artifact requires ml-engine {artifact_engine}, current version is {current_engine}"
        )

    recorded_dependencies = manifest.get("estimator_library_versions", {})
    if isinstance(recorded_dependencies, Mapping):
        for distribution, recorded in recorded_dependencies.items():
            if not isinstance(distribution, str) or not isinstance(recorded, str):
                continue
            recorded_match = _VERSION_RE.match(recorded)
            if recorded_match is None:
                continue
            try:
                current = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                continue
            current_match = _VERSION_RE.match(current)
            if current_match is not None and int(recorded_match.group(1)) != int(
                current_match.group(1)
            ):
                raise ArtifactCompatibilityError(
                    f"artifact requires {distribution} {recorded}, current version is {current}"
                )
