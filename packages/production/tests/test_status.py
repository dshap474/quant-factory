"""Test provider-neutral authority and runtime-journal status facts.

USAGE: ``uv run --package quant-factory-production pytest packages/production/tests/test_status.py -q``.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import production.status as status_module
import pytest
from production.contracts import ActivationReceipt
from production.registry import (
    FamilyPolicy,
    RuntimeAdapter,
    RuntimeExecutionResult,
    UnknownRuntimeAdapterError,
    register_family_policy,
    register_runtime_adapter,
    runtime_adapter,
)
from production.status import production_status

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

VENUE = "example-status-venue"
INCOMPATIBLE_VENUE = "incompatible-status-venue"
FAMILY = "example-status-family"


def _command(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess((), returncode, stdout=stdout, stderr="")


def _register_adapter(venue: str, compatible: bool) -> None:
    try:
        runtime_adapter(venue)
    except UnknownRuntimeAdapterError:
        register_runtime_adapter(
            RuntimeAdapter(
                venue_id=venue,
                host_trading_gate="EXAMPLE_STATUS_TRADING_ENABLED",
                dry_run_activation_required=True,
                activation_compatible=lambda definition, activation: (
                    compatible and isinstance(activation, ActivationReceipt)
                ),
                execute=lambda context, refresh: RuntimeExecutionResult(execution={}),
            )
        )


@pytest.fixture(scope="module", autouse=True)
def _register_status_policy() -> None:
    _register_adapter(VENUE, True)
    _register_adapter(INCOMPATIBLE_VENUE, False)
    register_family_policy(FamilyPolicy(family_id=FAMILY, capital_gates=("EXAMPLE_CAPITAL_APPROVED",)))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_status_reports_can_trade_but_never_scheduled(monkeypatch, tmp_path: Path) -> None:
    fingerprint = "a" * 64
    deployment = tmp_path / FAMILY / "deployment.yaml"
    deployment.parent.mkdir(parents=True)
    deployment.write_text("fixture\n")
    state = tmp_path / "state"
    activation = state / "activations" / f"{fingerprint}.yaml"
    activation.parent.mkdir(parents=True)
    activation.write_text(
        f"""schema_version: 1
deployment_fingerprint: {fingerprint}
mode: live
account_id: external-account
max_position_notional_usd: "5"
max_order_notional_usd: "2"
expires_at: "2026-01-03T00:00:00Z"
enabled: true
"""
    )
    armed = state / "armed" / fingerprint
    armed.parent.mkdir(parents=True)
    armed.write_text("armed\n")
    definition = SimpleNamespace(
        strategy=SimpleNamespace(family=FAMILY),
        execution=SimpleNamespace(venue=VENUE),
    )
    monkeypatch.setattr(status_module, "validate_deployment", lambda path, root: definition)
    monkeypatch.setattr(status_module, "deployment_fingerprint", lambda path, root: fingerprint)

    def run_command(command):
        if command[0] == "git":
            return _command("b" * 40 + "\n")
        raise AssertionError(command)

    facts = dict(
        production_status(
            deployment,
            tmp_path,
            state,
            now=datetime(2026, 1, 2, tzinfo=UTC),
            environ={
                "EXAMPLE_STATUS_TRADING_ENABLED": "1",
                "EXAMPLE_CAPITAL_APPROVED": "1",
            },
            run_command=run_command,
        )
    )
    assert facts["CAN_TRADE"] == "yes"
    assert facts["SCHEDULED"] == "no"
    assert facts["AUTONOMOUS_LIVE"] == "no"
    assert facts["CAPITAL_APPROVAL"] == "open"

    definition.execution.venue = INCOMPATIBLE_VENUE
    incompatible = dict(
        production_status(
            deployment,
            tmp_path,
            state,
            now=datetime(2026, 1, 2, tzinfo=UTC),
            environ={
                "EXAMPLE_STATUS_TRADING_ENABLED": "1",
                "EXAMPLE_CAPITAL_APPROVED": "1",
            },
            run_command=run_command,
        )
    )
    assert incompatible["ACTIVATION_RECEIPT"] == "wrong-schema"
    assert incompatible["CAN_TRADE"] == "no"


def test_host_readers_do_not_inherit_process_environment(monkeypatch) -> None:
    captured = {}

    def run(command, **kwargs):
        captured.update(kwargs["env"])
        return _command("ok\n")

    monkeypatch.setattr(status_module.subprocess, "run", run)
    monkeypatch.setenv("EXAMPLE_PRIVATE_KEY", "must-not-propagate")
    status_module._run_command(("git", "--version"))
    assert "EXAMPLE_PRIVATE_KEY" not in captured
    assert set(captured) == {"PATH", "LANG", "LC_ALL"}
