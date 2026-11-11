"""Validated signal research-version surfaces for API and frontend discovery.

A version run publishes one immutable surface: per arm, the IC series and quantile returns
the frontend charts plus a flat metrics record, and a version-level ``surface.json`` pointer
that selects it. Arms compare the unchanged control against candidates. An arm may omit the IC
series or quantile table when its run did not produce one (e.g. a single-asset validation that
saved per-horizon summaries as flat metrics such as ``h7_auc``); the manifest records the
missing table as ``null``. A run that stopped at a blocker publishes state ``not_tested`` with
no arms and the ``blocker`` text.

Layout::

    db/research/signals/<family>/<version>/surface.json             pointer
    .../<experiment>/<run-id>/surface/manifest.json                  run record
    .../<experiment>/<run-id>/surface/arms/<arm>/ic.parquet          decision_time, target_id, ic (optional)
    .../<experiment>/<run-id>/surface/arms/<arm>/quantiles.parquet   target_id, quantile, label, mean_target, n (optional)
    .../<experiment>/<run-id>/surface/arms/<arm>/metrics.json        flat name -> number | null

USAGE::
    publish_research_surface(
        db_root, signal_family="family", memory_version="v003", experiment="example-ic",
        run_id=run_id, state="candidate", title="...", summary="...", primary_target="fwd_ret_h5",
        arms=[SurfaceArm("control", "v002 control", "control", ic, quantiles, metrics), ...],
    )
    publish_research_surface(
        db_root, signal_family="family", memory_version="v004", experiment="example-ic",
        run_id=run_id, state="not_tested", title="...", summary="...", arms=[],
        blocker="input X is missing before the start date",
    )
    surface = load_research_surface(db_root, "family", "v003")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import contextlib
import json
import math
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl

from .ids import validate_identifier

ResearchVersionState = Literal["candidate", "rejected", "not_tested"]
ArmRole = Literal["control", "candidate"]

# Optional arm tables and not_tested are additive: every v1 manifest still reads as before.
SCHEMA_VERSION = 1
_STATES = frozenset({"candidate", "rejected", "not_tested"})
_VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_UTC = pl.Datetime("us", "UTC")
IC_SCHEMA = pl.Schema({"decision_time": _UTC, "target_id": pl.String, "ic": pl.Float64})
QUANTILE_SCHEMA = pl.Schema(
    {
        "target_id": pl.String,
        "quantile": pl.Int64,
        "label": pl.String,
        "mean_target": pl.Float64,
        "n": pl.Int64,
    }
)
# AGENTS.md §5 "Run outputs": a run folder over 1 GB is wrong.
MAX_RUN_BYTES = 1 << 30


@dataclass(frozen=True)
class SurfaceArm:
    """One evaluated arm: its IC series, quantile returns, and flat metrics.

    ``ic`` or ``quantiles`` is ``None`` when this run did not produce that table.
    """

    arm_id: str
    label: str
    role: ArmRole
    ic: pl.DataFrame | None
    quantiles: pl.DataFrame | None
    metrics: Mapping[str, float | None] = field(default_factory=dict)
    description: str = ""


# --------------------------------------------------------------------------- #
# Atomic files and validation
# --------------------------------------------------------------------------- #


def _temporary_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = _temporary_path(path)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
        temporary.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _write_parquet_atomic(path: Path, frame: pl.DataFrame) -> None:
    temporary = _temporary_path(path)
    try:
        frame.write_parquet(temporary, compression="zstd", compression_level=3)
        temporary.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _validate_version(memory_version: str) -> None:
    if _VERSION_PATTERN.fullmatch(memory_version) is None:
        raise ValueError(f"memory_version must look like v001, got {memory_version!r}")


def _check_run_size(run_root: Path) -> None:
    """Refuse to publish a run folder over MAX_RUN_BYTES (AGENTS.md §5 "Run outputs")."""
    size = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file()) if run_root.is_dir() else 0
    if size > MAX_RUN_BYTES:
        raise ValueError(
            f"research run is {size / 1e9:.2f} GB, over the {MAX_RUN_BYTES / 1e9:.2f} GB limit: {run_root}. "
            "Save standard outputs only; rebuild model internals with the version's rerun.py"
        )


def _resolve_inside(root: Path, relative_path: str, *, label: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes its version directory") from error
    return target


def _conform(frame: pl.DataFrame, schema: pl.Schema, *, label: str) -> pl.DataFrame:
    missing = [name for name in schema if name not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing columns {missing}")
    try:
        return frame.select([pl.col(name).cast(dtype, strict=True) for name, dtype in schema.items()])
    except pl.exceptions.PolarsError as error:
        raise ValueError(f"{label} columns do not cast to {dict(schema)}") from error


def validate_ic_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Return the IC series in canonical order; ``ic`` may be null, never non-finite."""
    normalized = _conform(frame, IC_SCHEMA, label="ic")
    if normalized.height == 0:
        raise ValueError("ic must contain at least one row")
    if normalized.select(pl.col("decision_time").is_null().any() | pl.col("target_id").is_null().any()).item():
        raise ValueError("ic decision_time and target_id must be non-null")
    if normalized.select(pl.col("ic").is_infinite().any() | pl.col("ic").is_nan().any()).item():
        raise ValueError("ic values must be finite or null")
    if normalized.select(pl.struct("decision_time", "target_id").is_duplicated().any()).item():
        raise ValueError("ic must have one row per decision_time and target_id")
    return normalized.sort("target_id", "decision_time")


def validate_quantile_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Return quantile returns in canonical order: one row per target and ordered bucket."""
    normalized = _conform(frame, QUANTILE_SCHEMA, label="quantiles")
    if normalized.height == 0:
        raise ValueError("quantiles must contain at least one row")
    if normalized.select(pl.any_horizontal(pl.col("target_id", "quantile", "label", "n").is_null()).any()).item():
        raise ValueError("quantiles target_id, quantile, label and n must be non-null")
    if normalized.select(pl.col("mean_target").is_infinite().any() | pl.col("mean_target").is_nan().any()).item():
        raise ValueError("quantiles mean_target must be finite or null")
    if normalized.select(pl.struct("target_id", "quantile").is_duplicated().any()).item():
        raise ValueError("quantiles must have one row per target_id and quantile")
    return normalized.sort("target_id", "quantile")


def validate_metrics(metrics: Mapping[str, Any], *, label: str = "metrics") -> dict[str, float | None]:
    """Return a flat metric mapping of finite numbers or nulls."""
    if not isinstance(metrics, Mapping):
        raise ValueError(f"{label} must be an object")
    validated: dict[str, float | None] = {}
    for key, value in metrics.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be non-empty strings")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
        ):
            raise ValueError(f"{label}.{key} must be a finite number or null")
        validated[key] = None if value is None else float(value)
    return validated


def _validate_gates(gates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validated = []
    for gate in gates:
        name = gate.get("name")
        if not isinstance(name, str) or not name or not isinstance(gate.get("passed"), bool):
            raise ValueError("each gate needs a non-empty name and a boolean passed")
        validated.append(dict(gate))
    return validated


def _validate_arms(arms: Sequence[SurfaceArm], state: str, blocker: str | None) -> None:
    if state == "not_tested":
        if arms:
            raise ValueError("a not_tested research surface has no arms")
        if not isinstance(blocker, str) or not blocker.strip():
            raise ValueError("a not_tested research surface needs a blocker")
        return
    if blocker is not None:
        raise ValueError("only a not_tested research surface records a blocker")
    if not arms:
        raise ValueError("a signal research surface needs at least one arm")
    seen: set[str] = set()
    for arm in arms:
        validate_identifier(arm.arm_id, "arm_id")
        if arm.arm_id in seen:
            raise ValueError(f"duplicate arm_id {arm.arm_id!r}")
        seen.add(arm.arm_id)
        if arm.role not in {"control", "candidate"}:
            raise ValueError("arm role must be 'control' or 'candidate'")
        if not arm.label.strip():
            raise ValueError("arm label is required")
        if arm.ic is None and arm.quantiles is None and not arm.metrics:
            raise ValueError(f"arm {arm.arm_id!r} has no IC series, quantiles, or metrics")
    if sum(arm.role == "control" for arm in arms) > 1:
        raise ValueError("a signal research surface has at most one control arm")


# --------------------------------------------------------------------------- #
# Publication
# --------------------------------------------------------------------------- #


def publish_research_surface(
    db_root: Path,
    *,
    signal_family: str,
    memory_version: str,
    experiment: str,
    run_id: str,
    state: ResearchVersionState,
    title: str,
    summary: str,
    arms: Sequence[SurfaceArm],
    headline: Mapping[str, Any] | None = None,
    gates: Sequence[Mapping[str, Any]] = (),
    disclosures: Sequence[str] = (),
    provenance: Sequence[Mapping[str, str]] = (),
    blocker: str | None = None,
    primary_target: str | None = None,
    published_at: datetime | None = None,
) -> Path:
    """Publish one immutable signal research surface and select it for its version."""
    validate_identifier(signal_family, "signal_family")
    _validate_version(memory_version)
    validate_identifier(experiment, "experiment")
    if not _SAFE_SLUG.fullmatch(run_id):
        raise ValueError("run_id must be a filesystem-safe slug")
    if state not in _STATES:
        raise ValueError("research surface state must be 'candidate', 'rejected' or 'not_tested'")
    if not title.strip() or not summary.strip():
        raise ValueError("research surface title and summary are required")
    _validate_arms(arms, state, blocker)
    if primary_target is not None and not any(
        frame is not None and primary_target in frame["target_id"].to_list()
        for arm in arms
        for frame in (arm.ic, arm.quantiles)
    ):
        raise ValueError(f"primary_target {primary_target!r} is not a target of any arm")
    validated_gates = _validate_gates(gates)
    # Validate every arm before writing anything, so a bad arm never leaves a partial surface.
    normalized = [
        (
            arm,
            None if arm.ic is None else validate_ic_frame(arm.ic),
            None if arm.quantiles is None else validate_quantile_frame(arm.quantiles),
            validate_metrics(arm.metrics, label=f"{arm.arm_id}.metrics"),
        )
        for arm in arms
    ]

    version_root = Path(db_root) / "research" / "signals" / signal_family / memory_version
    run_root = version_root / experiment / run_id
    if not run_root.is_dir():
        raise FileNotFoundError(f"research run directory not found: {run_root}")
    surface_root = run_root / "surface"
    if surface_root.exists():
        raise FileExistsError(f"immutable research surface already exists: {surface_root}")
    _check_run_size(run_root)

    def write_table(arm_root: Path, name: str, frame: pl.DataFrame | None) -> dict[str, Any] | None:
        if frame is None:
            return None
        path = arm_root / f"{name}.parquet"
        _write_parquet_atomic(path, frame)
        return {"path": path.relative_to(version_root).as_posix(), "row_count": frame.height}

    arm_records = []
    for arm, ic, quantiles, metrics in normalized:
        arm_root = surface_root / "arms" / arm.arm_id
        metrics_path = arm_root / "metrics.json"
        _write_json_atomic(metrics_path, metrics)
        target_frames = [frame for frame in (ic, quantiles) if frame is not None]
        targets = (
            pl.concat([frame.select("target_id") for frame in target_frames])["target_id"]
            .unique(maintain_order=True)
            .to_list()
            if target_frames
            else []
        )
        arm_records.append(
            {
                "arm_id": arm.arm_id,
                "label": arm.label,
                "role": arm.role,
                "description": arm.description,
                "targets": targets,
                "ic": write_table(arm_root, "ic", ic),
                "quantiles": write_table(arm_root, "quantiles", quantiles),
                "metrics": {"path": metrics_path.relative_to(version_root).as_posix()},
            }
        )

    timestamp = (published_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    manifest_path = surface_root / "manifest.json"
    _write_json_atomic(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "signal_family": signal_family,
            "memory_version": memory_version,
            "state": state,
            "experiment": experiment,
            "run_id": run_id,
            "published_at": timestamp,
            "title": title,
            "summary": summary,
            "headline": dict(headline) if headline is not None else None,
            "blocker": blocker,
            "primary_target": primary_target,
            "arms": arm_records,
            "gates": validated_gates,
            "disclosures": list(disclosures),
            "provenance": [dict(item) for item in provenance],
        },
    )
    pointer_path = version_root / "surface.json"
    _write_json_atomic(
        pointer_path,
        {
            "schema_version": SCHEMA_VERSION,
            "signal_family": signal_family,
            "memory_version": memory_version,
            "state": state,
            "selected_manifest": manifest_path.relative_to(version_root).as_posix(),
            "published_at": timestamp,
        },
    )
    return pointer_path


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_research_surface(db_root: Path, signal_family: str, memory_version: str) -> dict[str, Any] | None:
    """Load and validate the selected surface manifest for one version, or ``None``."""
    validate_identifier(signal_family, "signal_family")
    _validate_version(memory_version)
    version_root = Path(db_root) / "research" / "signals" / signal_family / memory_version
    pointer_path = version_root / "surface.json"
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text())
    if not isinstance(pointer, dict) or pointer.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid research surface pointer: {pointer_path}")
    manifest_path = _resolve_inside(
        version_root, str(pointer.get("selected_manifest") or ""), label="selected_manifest"
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"research surface manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid research surface manifest: {manifest_path}")
    for payload in (pointer, manifest):
        if payload.get("signal_family") != signal_family or payload.get("memory_version") != memory_version:
            raise ValueError("research surface identity does not match its directory")
    if pointer.get("state") != manifest.get("state") or manifest.get("state") not in _STATES:
        raise ValueError("research surface has an invalid or mismatched state")
    required_text = ("experiment", "run_id", "published_at", "title", "summary")
    if any(not isinstance(manifest.get(key), str) or not manifest[key] for key in required_text):
        raise ValueError("research surface manifest is missing required text fields")
    if not all(isinstance(manifest.get(key), list) for key in ("arms", "gates", "disclosures", "provenance")):
        raise ValueError("research surface manifest has invalid collections")
    # Manifests written before not_tested existed have no blocker key.
    manifest.setdefault("blocker", None)
    # Manifests written before primary_target existed open on the first target.
    manifest.setdefault("primary_target", None)
    if manifest["state"] == "not_tested":
        if manifest["arms"] or not isinstance(manifest["blocker"], str) or not manifest["blocker"]:
            raise ValueError("a not_tested research surface has no arms and a blocker")
    elif not manifest["arms"]:
        raise ValueError("research surface manifest has no arms")
    for arm in manifest["arms"]:
        if not isinstance(arm, dict):
            raise ValueError("research surface arm must be an object")
        for table in ("ic", "quantiles", "metrics"):
            meta = arm.get(table)
            if meta is None and table in arm and table != "metrics":
                continue
            if not isinstance(meta, dict):
                raise ValueError(f"research surface arm is missing {table}")
            path = _resolve_inside(version_root, str(meta.get("path") or ""), label=f"{table}.path")
            if not path.is_file():
                raise FileNotFoundError(f"research surface {table} not found: {path}")
        arm["metrics"]["values"] = validate_metrics(
            json.loads(_resolve_inside(version_root, arm["metrics"]["path"], label="metrics.path").read_text())
        )
    return manifest


def load_surface_table(
    db_root: Path, signal_family: str, memory_version: str, arm_id: str, table: Literal["ic", "quantiles"]
) -> pl.DataFrame | None:
    """Load one validated arm table from the selected surface; ``None`` if this run did not produce it."""
    manifest = load_research_surface(db_root, signal_family, memory_version)
    if manifest is None:
        raise FileNotFoundError(f"no research surface for {signal_family} {memory_version}")
    arm = next((item for item in manifest["arms"] if item.get("arm_id") == arm_id), None)
    if arm is None:
        raise KeyError(f"arm {arm_id!r} is not in the research surface")
    if arm[table] is None:
        return None
    version_root = Path(db_root) / "research" / "signals" / signal_family / memory_version
    path = _resolve_inside(version_root, arm[table]["path"], label=f"{table}.path")
    frame = pl.read_parquet(path)
    if frame.height != arm[table].get("row_count"):
        raise ValueError(f"research surface {table} row count does not match its manifest")
    return validate_ic_frame(frame) if table == "ic" else validate_quantile_frame(frame)
