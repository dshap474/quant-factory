"""Crash-safe append-only JSONL write-ahead journal for one live run.

Purpose: record intent / attempt / submit / fill / reconcile / halt facts
before state transitions take effect. Durability: flush + fsync on every
append; fsync file and parent directory on create. Replay truncates a torn
trailing record; a malformed interior record fails closed.

USAGE:
    from pathlib import Path
    from execution.journal import RunJournal
    j = RunJournal(state_root=Path("/tmp/run"), run_id="r1")
    j.append({"type": "intent", "slice_id": "s1"})
    records = j.replay()
    j.require_no_live_attempt()      # refuse a reused run id
    j.unfinished_attempts()          # attempts never reconciled or halted
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from execution._checks import require_non_empty_str

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

UTC = timezone.utc
RECORD_TYPES = frozenset(
    {
        "intent",
        "attempt_created",
        "submit_result",
        "ws_event",
        "transition",
        "fill",
        "reconcile",
        "halt",
        "arm",
        "telemetry_note",
    }
)

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class JournalError(Exception):
    """Base journal failure."""


class JournalCorruptError(JournalError):
    """Malformed interior record — fail closed (do not truncate past it)."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def fsync_dir(path: Path) -> None:
    """Durably persist a directory entry (after create/rename inside it)."""
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_filename_part(value: str) -> str:
    """Reduce an id to filename-safe characters."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value)


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class RunJournal:
    """One-file-per-run append-only JSONL journal under a caller state root."""

    state_root: Path
    run_id: str
    _path: Path | None = None
    _fh: Any = None

    def __post_init__(self) -> None:
        require_non_empty_str(self.run_id, "run_id")
        if not isinstance(self.state_root, Path):
            object.__setattr__(self, "state_root", Path(self.state_root))

    @property
    def path(self) -> Path:
        if self._path is None:
            self._path = self.state_root / f"journal.{safe_filename_part(self.run_id)}.jsonl"
        return self._path

    def open(self) -> None:
        """Create or open the journal file; durable create when new."""
        self.state_root.mkdir(parents=True, exist_ok=True)
        fsync_dir(self.state_root)
        existed = self.path.exists()
        self._fh = self.path.open("a+", encoding="utf-8")
        if not existed:
            self._fh.flush()
            os.fsync(self._fh.fileno())
            fsync_dir(self.state_root)

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                os.fsync(self._fh.fileno())
            finally:
                self._fh.close()
                self._fh = None

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Append one record with flush+fsync before return (before transition)."""
        if self._fh is None:
            self.open()
        payload = dict(record)
        rtype = payload.get("type")
        if rtype not in RECORD_TYPES:
            raise ValueError(f"unknown journal record type: {rtype!r}")
        if "ts" not in payload:
            payload["ts"] = _utc_now_iso()
        line = json.dumps(payload, separators=(",", ":"), default=str) + "\n"
        assert self._fh is not None
        self._fh.write(line)
        self._fh.flush()
        os.fsync(self._fh.fileno())
        return payload

    def replay(self) -> list[dict[str, Any]]:
        """Replay all valid records. Truncate torn tail; fail on interior corrupt."""
        path = self.path
        if not path.exists():
            return []
        raw = path.read_bytes()
        if not raw:
            return []
        # Split keeping knowledge of trailing incomplete line.
        text = raw.decode("utf-8", errors="strict")
        # If file does not end with newline, trailing record is torn.
        torn = not text.endswith("\n")
        lines = text.split("\n")
        if torn:
            # Drop incomplete last fragment.
            incomplete = lines[-1]
            lines = lines[:-1]
        else:
            incomplete = ""
            # split leaves a trailing empty from final \n
            if lines and lines[-1] == "":
                lines = lines[:-1]

        records: list[dict[str, Any]] = []
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalCorruptError(f"malformed interior journal record at line {i + 1}: {exc}") from exc
            if not isinstance(obj, dict) or "type" not in obj:
                raise JournalCorruptError(f"malformed interior journal record at line {i + 1}: not a typed object")
            if obj["type"] not in RECORD_TYPES:
                raise JournalCorruptError(f"unknown record type at line {i + 1}: {obj['type']!r}")
            records.append(obj)

        if torn and incomplete.strip():
            # Truncate file to last complete line boundary.
            good = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
            with path.open("wb") as fh:
                fh.write(good)
                fh.flush()
                os.fsync(fh.fileno())
            # Re-open append handle if we had one.
            if self._fh is not None:
                self._fh.close()
                self._fh = path.open("a+", encoding="utf-8")

        return records

    def require_no_live_attempt(self) -> None:
        """Refuse to reuse a run whose journal already records a live order attempt."""
        if any(r["type"] == "attempt_created" and not r.get("dry_run") for r in self.replay()):
            raise ValueError("run journal already contains a live order attempt; use a new run_id")

    def unfinished_attempts(self) -> list[str]:
        """Client order ids with an ``attempt_created`` but no later ``reconcile`` or ``halt``."""
        attempts: set[str] = set()
        terminal: set[str] = set()
        for record in self.replay():
            if record["type"] not in {"attempt_created", "reconcile", "halt"}:
                continue
            client_order_id = record.get("client_order_id")
            if not isinstance(client_order_id, str) or not client_order_id:
                raise JournalCorruptError(f"{record['type']} record has no client_order_id")
            if record["type"] == "attempt_created":
                attempts.add(client_order_id)
                terminal.discard(client_order_id)
            elif client_order_id not in attempts:
                raise JournalCorruptError(f"terminal record for {client_order_id} precedes its attempt")
            else:
                terminal.add(client_order_id)
        return sorted(attempts - terminal)
