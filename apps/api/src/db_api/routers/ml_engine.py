"""Read-only ML Engine run-status and safe artifact-metadata routes.

USAGE::

    GET /api/ml-engine/runs
    GET /api/ml-engine/runs/{run_id}
    GET /api/ml-engine/producers

The router reads bounded JSON only.  It never imports estimators, opens Joblib
files, loads inference pipelines, or writes under ``db/ml-engine``.

Run IDs are timestamp-prefixed (``%Y%m%dT%H%M%S%fZ-<hex>``), so sidecar
filenames sort lexicographically by start time.  ``/runs`` walks that order
newest-first and stops once it holds enough records, which keeps an unfiltered
listing proportional to ``limit`` rather than to the size of the store.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import json
import os
import re
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..config import settings

router = APIRouter()

_MAX_JSON_BYTES = 2 * 1024 * 1024
_FILE_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
_DIRECTORY_OPEN_FLAGS = _FILE_OPEN_FLAGS | os.O_DIRECTORY
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# Filename order tracks start time only for timestamp-prefixed run IDs.  Read
# this many records past ``limit`` so an explicitly named run cannot displace a
# newer one from the returned page.
_SCAN_MARGIN = 50
_ARTIFACT_FILES = {
    "manifest": "manifest.json",
    "config": "config.json",
    "schema": "schema.json",
    "metrics": "metrics.json",
    "selection": "selection.json",
}


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


class MlEngineError(BaseModel):
    """Safe exception identity recorded by a tracked run."""

    model_config = ConfigDict(extra="forbid")

    type: str
    message: str


class MlEngineRun(BaseModel):
    """Validated v1 status sidecar projected to API consumers."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    producer: str
    status: Literal["running", "completed", "failed"]
    operation: str
    stage: Literal[
        "validation",
        "planning",
        "cross_validation",
        "evaluation",
        "selection",
        "ensemble",
        "final_refit",
        "artifact_save",
    ]
    task: str | None
    target: str | None
    feature_count: int | None = Field(default=None, ge=0)
    final_refit: bool | None
    candidate: str | None
    candidate_index: int | None = Field(default=None, ge=1)
    candidate_count: int | None = Field(default=None, ge=1)
    fold_index: int | None = Field(default=None, ge=1)
    fold_count: int | None = Field(default=None, ge=1)
    completed_fits: int = Field(ge=0)
    total_fits: int | None = Field(default=None, ge=0)
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    host: str
    inference_ready: bool
    error: MlEngineError | None

    @field_validator("started_at", "updated_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        """Reject naive or non-UTC timestamps before inventory sorting."""

        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value


class MlEngineRunList(BaseModel):
    """Newest-first run inventory with damaged-sidecar visibility.

    ``invalid_count`` reports the damaged sidecars seen by *this* bounded read,
    not the whole store; a newest-first page that stops early never examines
    older files and so cannot count them.
    """

    runs: list[MlEngineRun]
    count: int
    invalid_count: int


class MlEngineProducerList(BaseModel):
    """Every producer family in the store, independent of any run page."""

    producers: list[str]
    invalid_count: int


class MlEngineArtifact(BaseModel):
    """Allowlisted JSON metadata from one immutable inference artifact."""

    model_config = ConfigDict(populate_by_name=True)

    path: str
    manifest: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    schema_metadata: dict[str, Any] | None = Field(default=None, alias="schema")
    metrics: dict[str, Any] | None = None
    selection: dict[str, Any] | None = None


class MlEngineRunDetail(BaseModel):
    """One selected status and its optional safe artifact projection."""

    run: MlEngineRun
    artifact: MlEngineArtifact | None


# --------------------------------------------------------------------------- #
# Safe filesystem readers
# --------------------------------------------------------------------------- #


def _root() -> Path:
    """Return the configured operational root without creating it."""

    return settings.db_root / "ml-engine"


def _open_directory(path: str | Path, *, dir_fd: int | None = None) -> int:
    """Open one directory without following its final path component."""

    descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS, dir_fd=dir_fd)
    try:
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
    except BaseException:
        os.close(descriptor)
        raise
    if not is_directory:
        os.close(descriptor)
        raise ValueError("metadata path is not a directory")
    return descriptor


def _open_root() -> int | None:
    """Open the operational root safely, or return None when it is absent."""

    try:
        return _open_directory(_root())
    except FileNotFoundError:
        return None


def _read_json_object(filename: str, *, dir_fd: int) -> dict[str, Any]:
    """Read one direct-child regular JSON object without following symlinks."""

    descriptor = os.open(filename, _FILE_OPEN_FLAGS, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("metadata path is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(_MAX_JSON_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_JSON_BYTES:
        raise ValueError("metadata exceeds the JSON size limit")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return value


def _read_run(filename: str, *, root_fd: int) -> MlEngineRun:
    """Validate one sidecar and bind its declared ID to its filename."""

    run = MlEngineRun.model_validate(_read_json_object(filename, dir_fd=root_fd))
    if run.run_id != Path(filename).stem:
        raise ValueError("run ID does not match sidecar filename")
    return run


def _sidecar_filenames(root_fd: int) -> list[str]:
    """Return candidate sidecar names newest-first by run-ID timestamp prefix."""

    try:
        filenames = os.listdir(root_fd)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="ML Engine run metadata is invalid") from exc
    return sorted(
        (name for name in filenames if not name.startswith(".") and name.endswith(".json")),
        reverse=True,
    )


def _producer_matches(run: MlEngineRun, producer: str) -> bool:
    """Match a producer exactly or as a family prefix, never as a substring."""

    return run.producer == producer or run.producer.startswith(f"{producer}/")


def _discover_runs(
    *,
    limit: int,
    producer: str | None,
    status: str | None,
) -> tuple[list[MlEngineRun], int]:
    """Return one newest-first page without reading the whole store.

    An unfiltered page reads ``limit + _SCAN_MARGIN`` sidecars at most.  A
    filtered page keeps walking older files until it fills that budget, so a
    selective filter still degrades to a full scan in the worst case.
    """

    try:
        root_fd = _open_root()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="ML Engine run metadata is invalid") from exc
    if root_fd is None:
        return [], 0
    runs: list[MlEngineRun] = []
    invalid_count = 0
    try:
        for filename in _sidecar_filenames(root_fd):
            if len(runs) >= limit + _SCAN_MARGIN:
                break
            try:
                run = _read_run(filename, root_fd=root_fd)
            except (OSError, ValueError, json.JSONDecodeError, ValidationError):
                invalid_count += 1
                continue
            if producer is not None and not _producer_matches(run, producer):
                continue
            if status is not None and run.status != status:
                continue
            runs.append(run)
    finally:
        os.close(root_fd)
    runs.sort(key=lambda run: run.started_at, reverse=True)
    return runs[:limit], invalid_count


def _discover_producers() -> tuple[list[str], int]:
    """Return every producer family in the store with a whole-store scan.

    The run listing is intentionally window-bounded, so the operator filter
    cannot source its options from it; a family whose runs are all older than
    the newest page would silently disappear from the control.
    """

    try:
        root_fd = _open_root()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="ML Engine run metadata is invalid") from exc
    if root_fd is None:
        return [], 0
    families: set[str] = set()
    invalid_count = 0
    try:
        for filename in _sidecar_filenames(root_fd):
            try:
                payload = _read_json_object(filename, dir_fd=root_fd)
                producer = payload["producer"]
                if payload.get("schema_version") != 1 or not isinstance(producer, str):
                    raise ValueError("sidecar is not a supported v1 status record")
                if payload.get("run_id") != Path(filename).stem:
                    raise ValueError("run ID does not match sidecar filename")
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                invalid_count += 1
                continue
            families.add(producer.split("/", 1)[0])
    finally:
        os.close(root_fd)
    return sorted(families), invalid_count


def _artifact_metadata(run_id: str, *, root_fd: int) -> MlEngineArtifact | None:
    """Return allowlisted JSON fields without opening executable model state."""

    try:
        artifact_fd = _open_directory(run_id, dir_fd=root_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("artifact root is invalid") from exc
    values: dict[str, Any] = {"path": f"db/ml-engine/{run_id}"}
    try:
        for field, filename in _ARTIFACT_FILES.items():
            try:
                values[field] = _read_json_object(filename, dir_fd=artifact_fd)
            except FileNotFoundError:
                values[field] = None
    finally:
        os.close(artifact_fd)
    return MlEngineArtifact.model_validate(values)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/runs", response_model=MlEngineRunList)
def get_ml_engine_runs(
    limit: int = Query(default=50, ge=1, le=200),
    producer: str | None = Query(default=None, max_length=256),
    status: Literal["running", "completed", "failed"] | None = Query(default=None),
) -> MlEngineRunList:
    """List newest valid run sidecars while exposing invalid-file count.

    ``producer`` matches exactly or as a path prefix, so ``producer=family``
    selects every ``family/...`` run without pulling in ``family2/...``.
    Filtering happens during the bounded read, so a filter reaches runs older
    than an unfiltered page of the same ``limit`` would reach.
    """

    runs, invalid_count = _discover_runs(limit=limit, producer=producer, status=status)
    return MlEngineRunList(runs=runs, count=len(runs), invalid_count=invalid_count)


@router.get("/producers", response_model=MlEngineProducerList)
def get_ml_engine_producers() -> MlEngineProducerList:
    """List every producer family, so filter options survive a run flood."""

    producers, invalid_count = _discover_producers()
    return MlEngineProducerList(producers=producers, invalid_count=invalid_count)


@router.get("/runs/{run_id}", response_model=MlEngineRunDetail)
def get_ml_engine_run(run_id: str) -> MlEngineRunDetail:
    """Return one exact run and allowlisted artifact JSON metadata only."""

    if _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise HTTPException(status_code=404, detail="ML Engine run not found")
    try:
        root_fd = _open_root()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="ML Engine run metadata is invalid") from exc
    if root_fd is None:
        raise HTTPException(status_code=404, detail="ML Engine run not found")
    try:
        run = _read_run(f"{run_id}.json", root_fd=root_fd)
        artifact = _artifact_metadata(run_id, root_fd=root_fd)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="ML Engine run not found") from exc
    except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail="ML Engine run metadata is invalid") from exc
    finally:
        os.close(root_fd)
    return MlEngineRunDetail(run=run, artifact=artifact)
