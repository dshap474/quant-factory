"""Registry-driven publication of active signal families to ``db/signals``.

``publish_catalog`` is the generalized "run every active family with
``save=True``" capability behind ``qf-signals publish``. Selection comes from
the registry-derived catalog only; this module never names an extension family.

USAGE::

    >>> from pathlib import Path
    >>> from signals.publish import publish_catalog
    >>> report = publish_catalog(db_root=Path("/tmp/scratch/db"), dry_run=True)
    >>> report.exit_code
    0

Every runner emits one JSON line to stdout and, unless ``dry_run`` is set, the
same line is appended to ``<db_root>/signals/publish.jsonl`` so the ledger shows
how many rows each publish actually added.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from signals.bootstrap import import_active_runner_modules, resolve_signal_runner
from signals.manifest import get_default_preset, get_presets_for_signal, iter_signal_entries

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

LEDGER_FILENAME = "publish.jsonl"
HISTORY_FILENAME = "predictions.parquet"

RECORD_FIELDS = (
    "at",
    "signal_type",
    "preset",
    "signal_id",
    "status",
    "rows",
    "first_timestamp",
    "last_timestamp",
    "rows_before",
    "rows_after",
    "run_id",
    "duration_s",
    "error",
)


# --------------------------------------------------------------------------- #
# Report shapes
# --------------------------------------------------------------------------- #


@dataclass
class SignalPublishReport:
    """Outcome of one ``publish_catalog`` invocation."""

    records: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0
    dry_run: bool = False

    @property
    def ok(self) -> list[dict[str, Any]]:
        return [record for record in self.records if record["status"] == "ok"]

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [record for record in self.records if record["status"] == "error"]

    @property
    def success(self) -> bool:
        return not self.errors

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1

    def summary(self) -> str:
        return f"{len(self.ok)} ok, {len(self.errors)} error, {self.elapsed_s:.1f}s elapsed"


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def _active_signal_types() -> list[str]:
    """Return every ``status == "active"`` catalog entry."""
    return [signal_type for signal_type, _ in iter_signal_entries(include_planned=False)]


def select_targets(
    *,
    signal_types: Sequence[str] | None = None,
    preset: str | None = None,
    all_presets: bool = False,
) -> list[tuple[str, str | None, str | None]]:
    """Resolve ``(signal_type, preset, selection_error)`` triples to publish.

    A selection error is carried rather than raised so one unresolvable family
    never hides the rest; usage errors (mutually exclusive flags) still raise.
    """
    if preset is not None and all_presets:
        raise ValueError("--preset and --all-presets are mutually exclusive")

    requested = list(signal_types or [])
    if preset is not None and len(requested) != 1:
        raise ValueError("--preset requires exactly one --signal-type")

    active = _active_signal_types()
    selected = requested or active

    targets: list[tuple[str, str | None, str | None]] = []
    for signal_type in selected:
        if signal_type not in active:
            targets.append((signal_type, None, f"signal type not found in the active catalog: {signal_type}"))
            continue
        if preset is not None:
            targets.append((signal_type, preset, None))
            continue
        if all_presets:
            names = get_presets_for_signal(signal_type)
            if not names:
                targets.append((signal_type, None, f"{signal_type}: presets_dir has no YAML presets"))
                continue
            targets.extend((signal_type, name, None) for name in names)
            continue
        default_preset = get_default_preset(signal_type)
        if default_preset is None:
            targets.append((signal_type, None, f"{signal_type}: missing or invalid default_preset"))
            continue
        targets.append((signal_type, default_preset, None))
    return targets


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


def _history_path(db_root: Path, signal_id: str) -> Path:
    return db_root / "signals" / signal_id / HISTORY_FILENAME


def _history_rows(db_root: Path, signal_id: str | None) -> int:
    """Return the persisted history length, or ``0`` when there is none yet."""
    if not signal_id:
        return 0
    path = _history_path(db_root, signal_id)
    if not path.is_file():
        return 0
    return int(pl.scan_parquet(path).select(pl.len()).collect().item())


def _record(**facts: Any) -> dict[str, Any]:
    """Return one ledger record with the frozen key set and stable order."""
    return {key: facts.get(key) for key in RECORD_FIELDS}


def _frame_bounds(predictions: pl.DataFrame | None) -> tuple[str | None, str | None]:
    if predictions is None or len(predictions) == 0 or "timestamp" not in predictions.columns:
        return None, None
    column = predictions["timestamp"]
    return str(column.min()), str(column.max())


def _emit(record: dict[str, Any]) -> None:
    print(json.dumps(record, sort_keys=True, default=str), flush=True)


def append_ledger(db_root: Path, record: dict[str, Any]) -> Path:
    """Append one record to ``<db_root>/signals/publish.jsonl``."""
    ledger_path = db_root / "signals" / LEDGER_FILENAME
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return ledger_path


# --------------------------------------------------------------------------- #
# Publication
# --------------------------------------------------------------------------- #


def _publish_one(
    signal_type: str,
    preset: str | None,
    *,
    db_root: Path,
    dry_run: bool,
    selection_error: str | None = None,
) -> dict[str, Any]:
    """Run one registered family preset and return its ledger record."""
    started = time.perf_counter()
    at = datetime.now(tz=UTC).isoformat()
    signal_id: str | None = None

    if preset is None or selection_error is not None:
        return _record(
            at=at,
            signal_type=signal_type,
            preset=preset,
            status="error",
            rows_before=0,
            rows_after=0,
            duration_s=round(time.perf_counter() - started, 3),
            error=selection_error or f"{signal_type}: preset not resolvable",
        )

    rows_before = 0
    try:
        runner = resolve_signal_runner(signal_type, preset, save=not dry_run, db_root=db_root)
        signal_id = runner.run_config.signal_id
        rows_before = _history_rows(db_root, signal_id)
        result = runner.run()
        first_timestamp, last_timestamp = _frame_bounds(result.predictions)
        return _record(
            at=at,
            signal_type=signal_type,
            preset=preset,
            signal_id=signal_id,
            status="ok",
            rows=len(result.predictions),
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            rows_before=rows_before,
            rows_after=_history_rows(db_root, signal_id),
            run_id=result.run_id,
            duration_s=round(time.perf_counter() - started, 3),
        )
    except Exception as exc:
        return _record(
            at=at,
            signal_type=signal_type,
            preset=preset,
            signal_id=signal_id,
            status="error",
            rows_before=rows_before,
            rows_after=_history_rows(db_root, signal_id),
            duration_s=round(time.perf_counter() - started, 3),
            error=f"{type(exc).__name__}: {exc}",
        )


def publish_catalog(
    *,
    signal_types: Sequence[str] | None = None,
    preset: str | None = None,
    all_presets: bool = False,
    db_root: Path | None = None,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> SignalPublishReport:
    """Run selected active families with ``save=True`` and record every outcome.

    Args:
        signal_types: Registered signal types to publish; empty selects every
            ``status == "active"`` catalog entry.
        preset: One preset name; valid only with exactly one signal type.
        all_presets: Publish every preset file in each family's ``presets_dir``.
        db_root: Persistence root; defaults to the runner default (``QUANT_DB_ROOT``).
        dry_run: Run with ``save=False`` and write no ledger.
        fail_fast: Stop at the first failing runner instead of continuing.

    Returns:
        A ``SignalPublishReport`` whose ``exit_code`` is 1 when any runner failed.
    """
    from signals.runner import DEFAULT_DB_ROOT

    resolved_root = Path(db_root) if db_root is not None else DEFAULT_DB_ROOT
    targets = select_targets(signal_types=signal_types, preset=preset, all_presets=all_presets)

    import_active_runner_modules(include_planned=False)

    started = time.perf_counter()
    report = SignalPublishReport(dry_run=dry_run)
    for signal_type, preset_name, selection_error in targets:
        record = _publish_one(
            signal_type,
            preset_name,
            db_root=resolved_root,
            dry_run=dry_run,
            selection_error=selection_error,
        )
        report.records.append(record)
        _emit(record)
        if not dry_run:
            append_ledger(resolved_root, record)
        if fail_fast and record["status"] == "error":
            break

    report.elapsed_s = round(time.perf_counter() - started, 3)
    print(report.summary(), flush=True)
    return report


__all__ = [
    "LEDGER_FILENAME",
    "RECORD_FIELDS",
    "SignalPublishReport",
    "append_ledger",
    "publish_catalog",
    "select_targets",
]
