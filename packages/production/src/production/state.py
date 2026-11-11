"""External activation, arming, deactivation, and run-journal state.

USAGE: set ``QF_PRODUCTION_STATE_ROOT`` to a durable directory outside Git.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from production.contracts import ActivationBinding, DeploymentValidationError
from production.registry import parse_activation_receipt

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

STATE_ROOT_ENV = "QF_PRODUCTION_STATE_ROOT"


def state_root_from_env() -> Path:
    """Resolve the explicitly configured durable state root."""
    value = os.environ.get(STATE_ROOT_ENV)
    if not value:
        raise DeploymentValidationError(f"{STATE_ROOT_ENV} must name a durable external state root")
    return Path(value).expanduser().resolve()


def validate_state_root(state_root: Path, repo_root: Path) -> Path:
    """Require mutable runtime state to live outside the repository."""
    resolved = state_root.expanduser().resolve()
    repository = repo_root.resolve()
    if resolved == repository or repository in resolved.parents:
        raise DeploymentValidationError(f"runtime state root must be outside the repository: {resolved}")
    return resolved


def activation_path(state_root: Path, fingerprint: str) -> Path:
    return state_root / "activations" / f"{fingerprint}.yaml"


def arming_path(state_root: Path, fingerprint: str) -> Path:
    return state_root / "armed" / fingerprint


def deactivation_path(state_root: Path, fingerprint: str) -> Path:
    return state_root / "deactivations" / f"{fingerprint}.json"


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


def load_activation(state_root: Path, fingerprint: str, *, now: datetime) -> ActivationBinding:
    """Load and validate the external receipt and independent deactivation state."""
    if deactivation_record(state_root, fingerprint) is not None:
        raise DeploymentValidationError("deployment is deactivated")
    receipt = load_activation_binding(state_root, fingerprint)
    receipt.validate_current(fingerprint=fingerprint, now=now)
    return receipt


def load_activation_binding(state_root: Path, fingerprint: str) -> ActivationBinding:
    """Load exact account and cap binding without requiring live activation."""
    path = activation_path(state_root, fingerprint)
    text = _read_regular_text(path, "activation receipt", missing_ok=True)
    if text is None:
        raise DeploymentValidationError(f"activation receipt does not exist: {path}")
    return _read_activation(path, fingerprint, text=text)


def find_activation_binding(state_root: Path, fingerprint: str) -> ActivationBinding | None:
    """Return a validated activation binding when its exact regular file exists."""
    path = activation_path(state_root, fingerprint)
    text = _read_regular_text(path, "activation receipt", missing_ok=True)
    return None if text is None else _read_activation(path, fingerprint, text=text)


def install_activation(source: Path, state_root: Path, fingerprint: str) -> Path:
    """Validate and atomically install one operator-protected activation receipt."""
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise DeploymentValidationError(f"could not open protected activation receipt: {source}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise DeploymentValidationError("activation receipt source must be a regular file, not a symlink")
        if metadata.st_uid != os.geteuid():
            raise DeploymentValidationError("activation receipt source must be owned by the current operator")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise DeploymentValidationError("activation receipt source must not be accessible by group or others")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            text = handle.read()
    except (OSError, UnicodeError) as exc:
        raise DeploymentValidationError(f"could not read activation receipt: {source}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _read_activation(source, fingerprint, text=text)
    destination = activation_path(state_root, fingerprint)
    _atomic_write(destination, text)
    return destination


def _read_activation(path: Path, fingerprint: str, *, text: str | None = None) -> ActivationBinding:
    """Parse and fingerprint-check a receipt without granting live authority."""
    try:
        raw = yaml.safe_load(text if text is not None else path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeploymentValidationError(f"could not read activation receipt: {path}") from exc
    if not isinstance(raw, dict):
        raise DeploymentValidationError("activation receipt must contain a mapping")
    receipt = parse_activation_receipt(raw)
    receipt.validate_binding(fingerprint=fingerprint)
    return receipt


def is_armed(state_root: Path, fingerprint: str) -> bool:
    """Return true only for an exact external arming marker."""
    text = _read_regular_text(arming_path(state_root, fingerprint), "arming marker", missing_ok=True)
    if text is None:
        return False
    if text != "armed\n":
        raise DeploymentValidationError("arming marker content is contradictory")
    return True


def deactivation_record(state_root: Path, fingerprint: str) -> datetime | None:
    """Return the validated deactivation timestamp when its exact record exists."""
    path = deactivation_path(state_root, fingerprint)
    text = _read_regular_text(path, "deactivation record", missing_ok=True)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeploymentValidationError("deactivation record content is contradictory") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"deployment_fingerprint", "deactivated_at"}
        or payload.get("deployment_fingerprint") != fingerprint
        or not isinstance(payload.get("deactivated_at"), str)
    ):
        raise DeploymentValidationError("deactivation record content is contradictory")
    try:
        timestamp = datetime.fromisoformat(payload["deactivated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeploymentValidationError("deactivation timestamp is contradictory") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise DeploymentValidationError("deactivation timestamp is contradictory")
    return timestamp.astimezone(UTC)


def deactivate(state_root: Path, fingerprint: str, *, at: datetime) -> Path:
    """Atomically stop new decisions without flattening or cancelling."""
    path = deactivation_path(state_root, fingerprint)
    _atomic_write(
        path,
        json.dumps(
            {"deployment_fingerprint": fingerprint, "deactivated_at": at.isoformat()},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return path


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #


def append_journal(state_root: Path, fingerprint: str, payload: dict[str, Any]) -> Path:
    """Append one fsynced, log-safe runtime fact."""
    path = state_root / "journals" / fingerprint / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def journal_entries(state_root: Path, fingerprint: str) -> tuple[dict[str, Any], ...]:
    """Return every validated JSON object in the runtime journal, oldest first."""
    path = state_root / "journals" / fingerprint / "runs.jsonl"
    text = _read_regular_text(path, "runtime journal", missing_ok=True)
    if text is None:
        return ()
    entries: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DeploymentValidationError(f"runtime journal is unreadable: {path}") from exc
        if not isinstance(payload, dict):
            raise DeploymentValidationError(f"runtime journal is unreadable: {path}")
        entries.append(payload)
    return tuple(entries)


def latest_journal_entry(state_root: Path, fingerprint: str) -> dict[str, Any] | None:
    """Return the latest validated JSON object from the runtime journal."""
    path = state_root / "journals" / fingerprint / "runs.jsonl"
    text = _read_regular_text(path, "runtime journal", missing_ok=True)
    if text is None:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise DeploymentValidationError(f"runtime journal is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise DeploymentValidationError(f"runtime journal is unreadable: {path}")
    return payload


# --------------------------------------------------------------------------- #
# Fail-closed file reader
# --------------------------------------------------------------------------- #


def _read_regular_text(path: Path, label: str, *, missing_ok: bool) -> str | None:
    """Read one regular file without following a final-component symlink."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    except OSError as exc:
        raise DeploymentValidationError(f"{label} is unreadable: {path}") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise DeploymentValidationError(f"{label} is not a regular file: {path}")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            return handle.read()
    except (OSError, UnicodeError) as exc:
        raise DeploymentValidationError(f"{label} is unreadable: {path}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


# --------------------------------------------------------------------------- #
# Atomic writer
# --------------------------------------------------------------------------- #


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


__all__ = [
    "STATE_ROOT_ENV",
    "activation_path",
    "append_journal",
    "arming_path",
    "deactivate",
    "deactivation_path",
    "deactivation_record",
    "find_activation_binding",
    "install_activation",
    "is_armed",
    "journal_entries",
    "latest_journal_entry",
    "load_activation",
    "load_activation_binding",
    "state_root_from_env",
    "validate_state_root",
]
