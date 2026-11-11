"""A4 in-process and fresh-process deterministic lifecycle stress.

Purpose: repeatedly construct, run, and dispose the immediate and TWAP public
engines and prove their complete traces never drift or leak process state.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a4_lifecycle.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .a1_world import trace_hash
from .a4_support import core_world, failure_then_success_fingerprint, replay_fingerprint, run_public_world

# --------------------------------------------------------------------------- #
# In-process lifecycle stress
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["immediate", "twap"])
def test_a4_one_hundred_in_process_replays_have_one_trace(kind: str) -> None:
    synthetic = core_world(kind)
    expected = trace_hash(run_public_world(synthetic))
    observed = {trace_hash(run_public_world(synthetic)) for _ in range(100)}
    assert observed == {expected}


@pytest.mark.parametrize("kind", ["immediate", "twap"])
def test_a4_twenty_five_in_process_failures_do_not_poison_next_run(kind: str) -> None:
    expected = replay_fingerprint(kind)
    observed = {failure_then_success_fingerprint(kind) for _ in range(25)}
    assert observed == {expected}


# --------------------------------------------------------------------------- #
# Fresh-process lifecycle stress
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["immediate", "twap"])
def test_a4_twenty_five_fresh_process_replays_have_one_trace(kind: str) -> None:
    expected_input, expected_trace = replay_fingerprint(kind)
    observed = _fresh_process_fingerprints(kind, count=25)
    assert observed == {(expected_input, expected_trace)}


@pytest.mark.parametrize("kind", ["immediate", "twap"])
def test_a4_twenty_five_fresh_process_failures_do_not_poison_next_run(kind: str) -> None:
    expected_input, expected_trace = replay_fingerprint(kind)
    observed = _fresh_process_fingerprints(f"failure-{kind}", count=25)
    assert observed == {(expected_input, expected_trace)}


def _fresh_process_fingerprints(mode: str, *, count: int) -> set[tuple[str, str]]:
    project_root = Path(__file__).resolve().parents[5]
    environment = os.environ.copy()
    python_path = str(project_root / "packages/platform/backtest/tests")
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (python_path, environment.get("PYTHONPATH"))))
    observed: set[tuple[str, str]] = set()
    for _ in range(count):
        completed = subprocess.run(
            [sys.executable, "-m", "audit.a4_replay", mode],
            cwd=project_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        if mode.startswith("failure-"):
            assert "below min_quantity" in completed.stderr
            assert "InvalidStateTrigger" not in completed.stderr
        else:
            assert completed.stderr == ""
        assert payload["scenario"] == mode
        observed.add((payload["input_hash"], payload["trace_hash"]))
    return observed
