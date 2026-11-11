"""Track one supervised training run with an atomic JSON status sidecar.

Usage::

    with TrainingRun(output_root="db/ml-engine", producer="example/v1") as run:
        result = TrainingPipeline(config).run(frame, progress=run.update)
        if config.final_refit:
            run.save(result)

The context owns one stable run ID and writes only its sibling status sidecar
and optional existing-format :class:`TrainingResult` artifact directory.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import socket
import sys
import tempfile
import uuid
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from .progress import TrainingProgress
from .result import TrainingResult


# --------------------------------------------------------------------------- #
# Run identity and serialization helpers
# --------------------------------------------------------------------------- #


_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _utc_now() -> str:
    """Return the canonical UTC timestamp used by status sidecars."""

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _new_run_id() -> str:
    """Generate one timestamped, collision-resistant run identity."""

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _validate_run_id(run_id: str) -> str:
    """Return a valid explicit run ID or fail before any filesystem write."""

    if not isinstance(run_id, str) or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError("run_id must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    return run_id


def _error_payload(
    exc_type: type[BaseException] | None, exc: BaseException | None
) -> dict[str, str]:
    """Return bounded exception identity without serializing a traceback."""

    name = exc_type.__name__ if exc_type is not None else "Exception"
    message = str(exc) if exc is not None else "Training failed"
    return {"type": name, "message": message[:4_096]}


# --------------------------------------------------------------------------- #
# Active-run registry
# --------------------------------------------------------------------------- #


_ACTIVE_RUN: contextvars.ContextVar["TrainingRun | None"] = contextvars.ContextVar(
    "ml_engine_active_training_run", default=None
)


def current_training_run() -> "TrainingRun | None":
    """Return the innermost active :class:`TrainingRun`, or ``None``."""

    return _ACTIVE_RUN.get()


# --------------------------------------------------------------------------- #
# Public tracked-run context
# --------------------------------------------------------------------------- #


class TrainingRun:
    """Own one run ID, live status sidecar, and canonical artifact path."""

    def __init__(
        self,
        *,
        output_root: str | os.PathLike[str],
        producer: str,
        run_id: str | None = None,
        operation: str = "training",
        host: str | None = None,
    ) -> None:
        if not isinstance(producer, str) or not producer.strip():
            raise ValueError("producer must be a non-empty string")
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation must be a non-empty string")
        self.output_root = Path(output_root)
        self.producer = producer.strip()
        self.run_id = _validate_run_id(run_id if run_id is not None else _new_run_id())
        self.operation = operation.strip()
        self.host = host.strip() if isinstance(host, str) and host.strip() else socket.gethostname()
        self.sidecar_path = self.output_root / f"{self.run_id}.json"
        self.artifact_path = self.output_root / self.run_id
        self._state: dict[str, Any] | None = None
        self._active = False
        self._context_token: contextvars.Token[TrainingRun | None] | None = None

    def __enter__(self) -> Self:
        """Create the initial running sidecar without reusing an existing ID."""

        self.output_root.mkdir(parents=True, exist_ok=True)
        if self.sidecar_path.exists() or self.artifact_path.exists():
            raise FileExistsError(f"ML Engine run ID already exists: {self.run_id}")
        started_at = _utc_now()
        self._state = {
            "schema_version": 1,
            "run_id": self.run_id,
            "producer": self.producer,
            "status": "running",
            "operation": self.operation,
            "stage": "validation",
            "task": None,
            "target": None,
            "feature_count": None,
            "final_refit": None,
            "candidate": None,
            "candidate_index": None,
            "candidate_count": None,
            "fold_index": None,
            "fold_count": None,
            "completed_fits": 0,
            "total_fits": None,
            "started_at": started_at,
            "updated_at": started_at,
            "completed_at": None,
            "host": self.host,
            "inference_ready": False,
            "error": None,
        }
        self._write_initial_state()
        self._active = True
        self._context_token = _ACTIVE_RUN.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Write one terminal state and always propagate the original exception."""

        if self._context_token is not None:
            _ACTIVE_RUN.reset(self._context_token)
            self._context_token = None
        if not self._active or self._state is None:
            return False
        terminal_at = _utc_now()
        self._state.update(
            {
                "status": "failed" if exc_type is not None else "completed",
                "updated_at": terminal_at,
                "completed_at": terminal_at,
                "error": _error_payload(exc_type, exc) if exc_type is not None else None,
            }
        )
        try:
            self._replace_state()
        except BaseException as write_error:
            self._active = False
            if exc is not None:
                raise exc.with_traceback(traceback) from write_error
            raise
        self._active = False
        return False

    def set_operation(self, operation: str) -> None:
        """Replace the current caller-defined operation without retaining history."""

        state = self._require_active()
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation must be a non-empty string")
        self.operation = operation.strip()
        state["operation"] = self.operation
        state["updated_at"] = _utc_now()
        self._replace_state()

    def update(self, progress: TrainingProgress) -> None:
        """Persist one immutable engine progress value atomically."""

        state = self._require_active()
        if not isinstance(progress, TrainingProgress):
            raise TypeError("progress must be a TrainingProgress")
        state.update(
            {
                "stage": progress.stage,
                "task": progress.task,
                "target": progress.target,
                "feature_count": progress.feature_count,
                "final_refit": progress.final_refit,
                "candidate": progress.candidate,
                "candidate_index": progress.candidate_index,
                "candidate_count": progress.candidate_count,
                "fold_index": progress.fold_index,
                "fold_count": progress.fold_count,
                "completed_fits": progress.completed_fits,
                "total_fits": progress.total_fits,
                "updated_at": _utc_now(),
            }
        )
        self._replace_state()

    def save(self, result: TrainingResult) -> Path:
        """Save one existing-format inference artifact under this run ID."""

        state = self._require_active()
        if not isinstance(result, TrainingResult):
            raise TypeError("result must be a TrainingResult")
        state.update({"stage": "artifact_save", "updated_at": _utc_now()})
        self._replace_state()
        destination = result.save(self.artifact_path)
        state.update({"inference_ready": True, "updated_at": _utc_now()})
        self._replace_state()
        return destination

    def _require_active(self) -> dict[str, Any]:
        """Return active mutable state or fail outside the context lifetime."""

        if not self._active or self._state is None:
            raise RuntimeError("TrainingRun is not active")
        return self._state

    def _serialized_state(self) -> bytes:
        """Return deterministic, newline-terminated sidecar bytes."""

        if self._state is None:
            raise RuntimeError("TrainingRun state has not been initialized")
        return (json.dumps(self._state, sort_keys=True, indent=2) + "\n").encode("utf-8")

    def _temporary_path(self) -> Path:
        """Reserve one dot-prefixed sibling temporary path."""

        descriptor, name = tempfile.mkstemp(
            prefix=f".{self.run_id}.",
            suffix=".tmp",
            dir=self.output_root,
        )
        os.close(descriptor)
        return Path(name)

    def _write_temporary(self) -> Path:
        """Write and fsync one complete sibling temporary sidecar."""

        temporary = self._temporary_path()
        try:
            with temporary.open("wb") as handle:
                handle.write(self._serialized_state())
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return temporary

    def _write_initial_state(self) -> None:
        """Atomically install the initial sidecar only when its ID is unused."""

        temporary = self._write_temporary()
        try:
            os.link(temporary, self.sidecar_path)
        except FileExistsError as exc:
            raise FileExistsError(f"ML Engine run ID already exists: {self.run_id}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _replace_state(self) -> None:
        """Atomically replace the current sidecar with one complete document."""

        temporary = self._write_temporary()
        try:
            os.replace(temporary, self.sidecar_path)
        finally:
            temporary.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Always-on auto-tracking
# --------------------------------------------------------------------------- #


def _auto_tracking_suppressed() -> bool:
    """Suppress implicit sidecars for opted-out processes and test runs."""

    if os.environ.get("ML_ENGINE_TRACKING", "").strip() == "0":
        return True
    return "PYTEST_CURRENT_TEST" in os.environ


def _auto_output_root() -> Path | None:
    """Resolve the canonical run store without importing repo-coupled config."""

    override = os.environ.get("ML_ENGINE_OUTPUT_ROOT", "").strip()
    if override:
        return Path(override)
    db_root = os.environ.get("QUANT_DB_ROOT", "").strip()
    if db_root:
        return Path(db_root) / "ml-engine"
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "db").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate / "db" / "ml-engine"
    return None


def _auto_producer() -> str:
    """Return the declared producer identity, or an honest unattributed one."""

    override = os.environ.get("ML_ENGINE_PRODUCER", "").strip()
    if override:
        return override
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else ""
    stem = Path(argv0).stem or "interactive"
    return f"unattributed/{stem}"


class AutoTrackingContext:
    """Guarantee one status sidecar per pipeline run without caller opt-in.

    Inside an explicit :class:`TrainingRun` the caller's run owns the sidecar and
    progress is forwarded to it; otherwise a best-effort implicit run is opened.
    Telemetry failures are recorded in :attr:`notices` for the pipeline to place
    on ``TrainingResult.warnings``. They also warn, and they do not fail training.
    """

    def __init__(self, progress: Callable[[TrainingProgress], None] | None) -> None:
        self._progress = progress
        self._auto_run: TrainingRun | None = None
        self._broken = False
        self.notices: list[str] = []

    def __enter__(self) -> Callable[[TrainingProgress], None] | None:
        active = current_training_run()
        if active is not None and active._active:
            if self._progress == active.update:
                return self._progress
            return self._combined(active.update)
        if _auto_tracking_suppressed():
            return self._progress
        try:
            root = _auto_output_root()
            if root is None:
                self._notice(
                    "ml-engine run tracking skipped: no output root "
                    "(set ML_ENGINE_OUTPUT_ROOT or QUANT_DB_ROOT)"
                )
                return self._progress
            run = TrainingRun(output_root=root, producer=_auto_producer())
            run.__enter__()
        except Exception as exc:  # noqa: BLE001 - telemetry must not fail training
            self._notice(f"ml-engine run tracking disabled for this run: {exc}")
            return self._progress
        self._auto_run = run
        return self._combined(run.update)

    def _combined(
        self,
        update: Callable[[TrainingProgress], None],
    ) -> Callable[[TrainingProgress], None]:
        caller = self._progress

        def forward(value: TrainingProgress) -> None:
            if caller is not None:
                caller(value)
            if self._broken:
                return
            try:
                update(value)
            except Exception as exc:  # noqa: BLE001 - telemetry must not fail training
                self._broken = True
                self._notice(f"ml-engine run tracking stopped mid-run: {exc}")

        return forward

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._auto_run is not None:
            try:
                self._auto_run.__exit__(exc_type, exc, traceback)
            except Exception as write_error:  # noqa: BLE001 - never mask training
                self._notice(f"ml-engine run sidecar finalization failed: {write_error}")
        return False

    def _notice(self, message: str) -> None:
        """Remember one tracking failure and warn. Training still proceeds."""

        self.notices.append(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


__all__ = ["AutoTrackingContext", "TrainingRun", "current_training_run"]
