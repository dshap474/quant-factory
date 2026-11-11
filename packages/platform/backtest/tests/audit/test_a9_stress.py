"""A9 resource, concurrency, environment, interruption, GC, and import stress.

Purpose: prove repeated and concurrent prepared engines remain deterministic,
bounded, process-isolated, and independent of ambient process configuration.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a9_stress.py -v
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psutil
import pytest

from .a1_world import trace_hash
from .a4_support import core_world, failure_then_success_fingerprint, replay_fingerprint, run_public_world

# --------------------------------------------------------------------------- #
# Frozen resource budgets
# --------------------------------------------------------------------------- #

RESOURCE_BATCH = 50
RESOURCE_CYCLES = 250
RSS_GROWTH_BUDGET = 64 * 1024 * 1024
TRACED_GROWTH_BUDGET = 8 * 1024 * 1024


def _child_environment(**changes: str) -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[5]
    environment = os.environ.copy()
    tests_path = str(project_root / "packages/platform/backtest/tests")
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (tests_path, environment.get("PYTHONPATH"))))
    environment.update(changes)
    return environment


def _child_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "audit.a9_replay", *args]


def _last_json(stdout: str) -> dict[str, object]:
    return json.loads(stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------------- #
# D03: resource stress
# --------------------------------------------------------------------------- #


def test_d03_clean_and_failure_success_cycles_have_bounded_resources() -> None:
    process = psutil.Process()
    expected_clean = replay_fingerprint("immediate")
    expected_successor = replay_fingerprint("twap")
    for _ in range(10):
        replay_fingerprint("immediate")
        failure_then_success_fingerprint("twap")
    gc.collect()
    baseline_fds = process.num_fds()
    baseline_rss = process.memory_info().rss
    tracemalloc.start()
    baseline_traced = tracemalloc.get_traced_memory()[0]
    samples: list[tuple[int, int, int]] = []
    try:
        for index in range(RESOURCE_CYCLES):
            assert replay_fingerprint("immediate") == expected_clean
            assert failure_then_success_fingerprint("twap") == expected_successor
            if (index + 1) % RESOURCE_BATCH == 0:
                gc.collect()
                samples.append((process.num_fds(), process.memory_info().rss, tracemalloc.get_traced_memory()[0]))
    finally:
        tracemalloc.stop()
    assert all(fds == baseline_fds for fds, _, _ in samples)
    assert max(rss for _, rss, _ in samples) - baseline_rss <= RSS_GROWTH_BUDGET
    assert max(traced for _, _, traced in samples) - baseline_traced <= TRACED_GROWTH_BUDGET
    assert samples[-1][1] - samples[-2][1] <= 8 * 1024 * 1024


# --------------------------------------------------------------------------- #
# D04-D06: process/thread/environment determinism
# --------------------------------------------------------------------------- #


def test_d04_eight_concurrent_processes_share_exact_batch_hashes() -> None:
    project_root = Path(__file__).resolve().parents[5]
    processes = [
        subprocess.Popen(
            _child_command("batch", "10", "immediate" if index % 2 == 0 else "twap"),
            cwd=project_root,
            env=_child_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(8)
    ]
    payloads = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=120)
        assert process.returncode == 0, stderr
        assert stderr == ""
        payloads.append(_last_json(stdout))
    assert all(payload == payloads[0] for payload in payloads)
    assert len(payloads[0]["immediate"]) == len(payloads[0]["twap"]) == 1


def test_d05_two_threaded_independent_runs_are_exact_or_explicitly_rejected() -> None:
    worlds = (core_world("immediate"), core_world("twap"))
    expected = tuple(trace_hash(run_public_world(world)) for world in worlds)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(lambda item=world: trace_hash(run_public_world(item))) for world in worlds]
        observed = tuple(future.result(timeout=30) for future in futures)
    assert observed == expected


@pytest.mark.parametrize(
    ("hash_seed", "timezone", "locale"),
    [
        ("0", "UTC", "C"),
        ("1", "America/Los_Angeles", "C"),
        ("42", "Asia/Tokyo", "C"),
        ("999", "Europe/London", "C"),
    ],
)
def test_d06_environment_changes_preserve_complete_hashes(hash_seed: str, timezone: str, locale: str) -> None:
    project_root = Path(__file__).resolve().parents[5]
    completed = subprocess.run(
        _child_command("batch", "2", "immediate"),
        cwd=project_root,
        env=_child_environment(PYTHONHASHSEED=hash_seed, TZ=timezone, LC_ALL=locale, LANG=locale),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = _last_json(completed.stdout)
    assert payload["immediate"] == [
        [
            "b140c2cbeddd5b16f3e49bb66809842ef7f68ee789aa89a67d63f1129af5e634",
            "1745c8d15ac6cb09a83b237757b46b729740ce3dde0ea3d23d7c42638b59e5cd",
        ]
    ]
    assert payload["twap"] == [
        [
            "54f6475e53d77f123235955a52c5520edfaea5be8a1cd97a8fe77dc5f654015f",
            "45bc7f1c2038629ecbc48f190573475c4f48d352af410a3a585670479ec12eef",
        ]
    ]


# --------------------------------------------------------------------------- #
# D07: forced process interruption
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("stage", ["construction", "execution", "assembly"])
def test_d07_terminated_child_cannot_poison_successor(stage: str) -> None:
    project_root = Path(__file__).resolve().parents[5]
    process = subprocess.Popen(
        _child_command("interrupt", stage),
        cwd=project_root,
        env=_child_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    ready = json.loads(process.stdout.readline())
    assert ready == {"ready": stage}
    process.terminate()
    process.wait(timeout=10)
    assert process.returncode is not None and process.returncode != 0
    completed = subprocess.run(
        _child_command("batch", "1", "immediate"),
        cwd=project_root,
        env=_child_environment(),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert _last_json(completed.stdout)["immediate"] == [
        [
            "b140c2cbeddd5b16f3e49bb66809842ef7f68ee789aa89a67d63f1129af5e634",
            "1745c8d15ac6cb09a83b237757b46b729740ce3dde0ea3d23d7c42638b59e5cd",
        ]
    ]


# --------------------------------------------------------------------------- #
# D09-D10: GC pressure and repeated import/runtime creation
# --------------------------------------------------------------------------- #


def test_d09_gc_pressure_does_not_change_prepared_traces() -> None:
    expected = replay_fingerprint("immediate")
    observed = set()
    for index in range(25):
        garbage = [bytearray(1024) for _ in range(1000)]
        if index % 2 == 0:
            gc.disable()
        observed.add(replay_fingerprint("immediate"))
        del garbage
        gc.enable()
        gc.collect()
    assert observed == {expected}


def test_d10_repeated_fresh_imports_preserve_versions_and_runtime() -> None:
    project_root = Path(__file__).resolve().parents[5]
    completed = subprocess.run(
        _child_command("imports", "25"),
        cwd=project_root,
        env=_child_environment(),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = _last_json(completed.stdout)
    assert payload["backtest_version"] == payload["execution_version"] == "0.1.0"
    assert payload["immediate"] == [
        "b140c2cbeddd5b16f3e49bb66809842ef7f68ee789aa89a67d63f1129af5e634",
        "1745c8d15ac6cb09a83b237757b46b729740ce3dde0ea3d23d7c42638b59e5cd",
    ]
