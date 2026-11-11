"""A9 runtime-stage lifecycle fault and cleanup regressions.

Purpose: inject deterministic failures throughout prepared runtime orchestration
and prove original errors, end/dispose ordering, and successor isolation.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a9_lifecycle_faults.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from backtest import BacktestConfig
from backtest.engines.nautilus import runtime
from backtest.errors import BacktestEngineExecutionError

from .a3_support import prepare, valid_packet
from .a4_support import replay_fingerprint

# --------------------------------------------------------------------------- #
# Fake runtime boundary
# --------------------------------------------------------------------------- #


class _Callable:
    def __init__(self, value: object = None) -> None:
        self.value = value

    def __call__(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        return self.value if self.value is not None else SimpleNamespace()


class _Cache:
    def orders(self) -> list[object]:
        return []


class _Engine:
    def __init__(self, fail_at: set[str], events: list[str]) -> None:
        self.fail_at = fail_at
        self.events = events
        self.cache = _Cache()

    def _step(self, name: str) -> None:
        self.events.append(name)
        if name in self.fail_at:
            raise RuntimeError(f"fault:{name}")

    def add_venue(self, **kwargs: object) -> None:
        del kwargs
        self._step("add_venue")

    def add_instrument(self, instrument: object) -> None:
        del instrument
        self._step("add_instrument")

    def add_data(self, bars: object) -> None:
        del bars
        self._step("add_data")

    def add_exec_algorithm(self, algorithm: object) -> None:
        del algorithm
        self._step("add_exec_algorithm")

    def add_strategy(self, strategy: object) -> None:
        del strategy
        self._step("add_strategy")

    def run(self) -> None:
        self._step("run")

    def end(self) -> None:
        self._step("end")

    def dispose(self) -> None:
        self._step("dispose")


def _install_fake_runtime(monkeypatch: pytest.MonkeyPatch, *, fail_at: str | set[str] | None) -> list[str]:
    events: list[str] = []
    failures = {fail_at} if isinstance(fail_at, str) else set(fail_at or ())
    engine = _Engine(failures, events)
    bundle: dict[str, Any] = {
        "BacktestEngine": lambda **kwargs: (
            _raise("engine_construction") if "engine_construction" in failures else engine
        ),
        "BacktestEngineConfig": _Callable(),
        "TraderId": _Callable(),
        "LoggingConfig": _Callable(),
        "Venue": _Callable(),
        "OmsType": SimpleNamespace(NETTING="NETTING"),
        "AccountType": SimpleNamespace(MARGIN="MARGIN"),
        "USDT": "USDT",
        "Money": _Callable(),
        "MakerTakerFeeModel": _Callable(),
        "BestPriceFillModel": _Callable(),
        "nautilus_version": "1.224.0",
    }
    monkeypatch.setattr(runtime, "import_nautilus_bundle", lambda: bundle)
    monkeypatch.setattr(runtime, "build_crypto_perpetual", lambda spec, nt: SimpleNamespace(id=spec.key.symbol))
    monkeypatch.setattr(runtime, "calendar_last_bar_type", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(runtime, "_build_all_bars", lambda *args, **kwargs: [])
    monkeypatch.setattr(runtime, "build_immediate_ioc_exec_algorithm", lambda nt: SimpleNamespace())
    monkeypatch.setattr(runtime, "build_execution_strategy", lambda state, nt: SimpleNamespace())
    monkeypatch.setattr(runtime, "attach_cache_orders", lambda state, orders: _maybe_raise(failures, "attach_cache"))
    monkeypatch.setattr(runtime, "_reconcile_end", lambda state, engine: _maybe_raise(failures, "reconcile"))
    monkeypatch.setattr(
        runtime,
        "terminalize_outcomes",
        lambda state, nt: _raise("terminalize") if "terminalize" in failures else (),
    )
    monkeypatch.setattr(runtime, "final_reconcile", lambda state: _maybe_raise(failures, "final_reconcile"))
    monkeypatch.setattr(
        runtime,
        "assemble_backtest_result",
        lambda **kwargs: _raise("assemble") if "assemble" in failures else SimpleNamespace(ok=True),
    )
    return events


def _raise(stage: str) -> Any:
    raise RuntimeError(f"fault:{stage}")


def _maybe_raise(failures: set[str], stage: str) -> None:
    if stage in failures:
        _raise(stage)


# --------------------------------------------------------------------------- #
# D01-D02: stage faults and cleanup
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "stage",
    [
        "add_venue",
        "add_instrument",
        "add_data",
        "add_exec_algorithm",
        "add_strategy",
        "run",
        "attach_cache",
        "reconcile",
        "terminalize",
        "final_reconcile",
        "assemble",
    ],
)
def test_d01_engine_stage_failure_preserves_cause_and_cleans_once(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    events = _install_fake_runtime(monkeypatch, fail_at=stage)
    with pytest.raises(BacktestEngineExecutionError, match=f"fault:{stage}"):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))
    assert events.count("end") == 1
    assert events.count("dispose") == 1
    assert events.index("end") < events.index("dispose")


def test_d01_engine_construction_failure_needs_no_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _install_fake_runtime(monkeypatch, fail_at="engine_construction")
    with pytest.raises(RuntimeError, match="fault:engine_construction"):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))
    assert events == []


@pytest.mark.parametrize("stage", ["import", "spec_map", "projection"])
def test_d01_pre_engine_failure_constructs_no_engine(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    if stage == "import":
        monkeypatch.setattr(runtime, "import_nautilus_bundle", lambda: _raise(stage))
    elif stage == "spec_map":
        monkeypatch.setattr(runtime, "_spec_map", lambda specs: _raise(stage))
    else:
        monkeypatch.setattr(runtime, "LinearPerpetualProjection", lambda **kwargs: _raise(stage))
    with pytest.raises(RuntimeError, match=f"fault:{stage}"):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))


@pytest.mark.parametrize("stage", ["end", "dispose"])
def test_d01_cleanup_failure_reports_stage(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    events = _install_fake_runtime(monkeypatch, fail_at=stage)
    with pytest.raises(BacktestEngineExecutionError, match=f"cleanup failed during {stage}"):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))
    assert events[-2:] == ["end", "dispose"]


def test_d01_primary_failure_is_not_masked_when_end_also_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _install_fake_runtime(monkeypatch, fail_at={"run", "end"})
    with pytest.raises(BacktestEngineExecutionError, match="fault:run"):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))
    assert "dispose" in events


@pytest.mark.parametrize(
    "stage",
    [
        "add_venue",
        "add_instrument",
        "add_data",
        "add_exec_algorithm",
        "add_strategy",
        "run",
        "attach_cache",
        "reconcile",
        "terminalize",
        "final_reconcile",
        "assemble",
        "end",
        "dispose",
    ],
)
def test_d02_every_constructed_failure_retains_in_and_fresh_process_hashes(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _install_fake_runtime(monkeypatch, fail_at=stage)
    with pytest.raises(BacktestEngineExecutionError):
        runtime.run_prepared_execution(prepared=prepare(valid_packet()), config=BacktestConfig(metrics=[]))
    monkeypatch.undo()
    assert replay_fingerprint("immediate")[1] == "1745c8d15ac6cb09a83b237757b46b729740ce3dde0ea3d23d7c42638b59e5cd"
    assert replay_fingerprint("twap")[1] == "45bc7f1c2038629ecbc48f190573475c4f48d352af410a3a585670479ec12eef"

    project_root = Path(__file__).resolve().parents[5]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "packages/platform/backtest/tests")
    completed = subprocess.run(
        [sys.executable, "-m", "audit.a9_replay", "batch", "1", "immediate"],
        cwd=project_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
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
