"""Hermetic tests for live journal durability and the OS run-lock.

USAGE: uv run --project packages/execution pytest packages/execution/tests/test_journal_lock.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from execution.journal import JournalCorruptError, RunJournal
from execution.locking import RunLock

_SRC = Path(__file__).resolve().parents[1] / "src"

# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #


def test_journal_fsync_and_replay(tmp_path: Path) -> None:
    j = RunJournal(state_root=tmp_path, run_id="j1")
    j.open()
    j.append({"type": "intent", "slice_id": "s1"})
    j.append({"type": "attempt_created", "client_order_id": "qf.x", "slice_id": "s1"})
    j.close()
    j2 = RunJournal(state_root=tmp_path, run_id="j1")
    j2.open()
    recs = j2.replay()
    assert len(recs) >= 2
    assert recs[0]["type"] == "intent"
    j2.close()


def test_journal_truncated_tail_replay(tmp_path: Path) -> None:
    j = RunJournal(state_root=tmp_path, run_id="j2")
    j.open()
    j.append({"type": "intent", "slice_id": "s"})
    path = j.path
    j.close()
    with open(path, "ab") as f:
        f.write(b'{"type": "torn')  # incomplete trailing line
    j2 = RunJournal(state_root=tmp_path, run_id="j2")
    j2.open()
    recs = j2.replay()
    assert any(r.get("type") == "intent" for r in recs)
    j2.close()


def test_journal_malformed_interior_fails_closed(tmp_path: Path) -> None:
    j = RunJournal(state_root=tmp_path, run_id="j3")
    j.open()
    j.append({"type": "intent", "slice_id": "s"})
    path = j.path
    j.close()
    raw = path.read_text()
    path.write_text(raw + "NOT_JSON\n" + json.dumps({"type": "halt", "reason": "x", "kind": "halted"}) + "\n")
    j2 = RunJournal(state_root=tmp_path, run_id="j3")
    j2.open()
    with pytest.raises(JournalCorruptError):
        j2.replay()
    j2.close()


def test_journal_restart_different_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    j = RunJournal(state_root=tmp_path, run_id="j4")
    j.open()
    j.append({"type": "intent", "slice_id": "s"})
    j.close()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    j2 = RunJournal(state_root=tmp_path, run_id="j4")
    j2.open()
    assert len(j2.replay()) >= 1
    j2.close()


# --------------------------------------------------------------------------- #
# Run lock
# --------------------------------------------------------------------------- #


def test_run_lock_second_process_refused(tmp_path: Path) -> None:
    lock_path = tmp_path / "run.lock"
    lock = RunLock(lock_path)
    lock.acquire()
    try:
        script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(_SRC)!r})
from execution.locking import RunLock, RunLockError
try:
    RunLock(Path({str(lock_path)!r})).acquire()
except RunLockError:
    raise SystemExit(2)
raise SystemExit(0)
"""
        env = {**os.environ, "PYTHONPATH": str(_SRC)}
        proc = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
        assert proc.returncode == 2
    finally:
        lock.release()


def test_run_lock_free_after_holder_exit(tmp_path: Path) -> None:
    lock_path = tmp_path / "run2.lock"
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(_SRC)!r})
from execution.locking import RunLock
RunLock(Path({str(lock_path)!r})).acquire()
# exit without release — OS should drop flock
"""
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    proc = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True)
    assert proc.returncode == 0
    lock = RunLock(lock_path)
    lock.acquire()
    lock.release()
