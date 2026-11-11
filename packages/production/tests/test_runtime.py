"""Test provider-neutral timing, authority, and adapter delegation.

USAGE: ``uv run --package quant-factory-production pytest packages/production/tests/test_runtime.py -q``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from production.contracts import ActivationReceipt, DeploymentDefinition, DeploymentValidationError
from production.deployment import deployment_fingerprint
from production.registry import (
    RuntimeAdapter,
    RuntimeExecutionContext,
    RuntimeExecutionResult,
    UnknownRuntimeAdapterError,
    register_runtime_adapter,
    runtime_adapter,
)
from production.runtime import run_once

from strategies import ExecutionTiming, RebalanceMode, StrategyWeights

# --------------------------------------------------------------------------- #
# Neutral adapter
# --------------------------------------------------------------------------- #

ADAPTER_ID = "example-venue"
HOST_GATE = "EXAMPLE_TRADING_ENABLED"
ADAPTER_CALLS: list[RuntimeExecutionContext] = []


def _compatible(definition: DeploymentDefinition, activation: object) -> bool:
    del definition
    return isinstance(activation, ActivationReceipt)


def _execute(context: RuntimeExecutionContext, refresh_authority) -> RuntimeExecutionResult:
    ADAPTER_CALLS.append(context)
    if context.live:
        assert refresh_authority() == context.activation
    return RuntimeExecutionResult(execution={"trustworthy": True, "symbol": context.symbol})


@pytest.fixture(scope="module", autouse=True)
def _register_adapter() -> None:
    try:
        runtime_adapter(ADAPTER_ID)
    except UnknownRuntimeAdapterError:
        register_runtime_adapter(
            RuntimeAdapter(
                venue_id=ADAPTER_ID,
                host_trading_gate=HOST_GATE,
                dry_run_activation_required=False,
                activation_compatible=_compatible,
                execute=_execute,
            )
        )


# --------------------------------------------------------------------------- #
# Repository and authority fixtures
# --------------------------------------------------------------------------- #


def _repository(tmp_path: Path, *, venue: str = ADAPTER_ID) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    family = repo / "packages/strategies/extensions/lib/example-family"
    (family / "optimization/v001").mkdir(parents=True)
    (family / "presets").mkdir()
    (family / "presets/default.yaml").write_text("name: default\n")
    runner = family / "src/example_family/runner.py"
    runner.parent.mkdir(parents=True)
    runner.write_text('"""fixture"""\n')
    (runner.parent / "__init__.py").write_text('"""fixture package"""\n')
    strategies_root = repo / "packages/strategies"
    strategies_root.mkdir(exist_ok=True)
    (strategies_root / "pyproject.toml").write_text(
        """[tool.hatch.build.targets.wheel]
packages = ["src/strategies"]
[tool.hatch.build.targets.sdist]
exclude = ["/extensions/**"]
"""
    )
    final = repo / "db/strategies/example-family/versions/v001/final"
    final.mkdir(parents=True)
    (final / "meta.json").write_text('{"selected_run_id":"run-1"}\n')
    (final / "promotion-receipt.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family": "example-family",
                "memory_version": "v001",
                "source_run_id": "run-1",
                "source_manifest_sha256": "a" * 64,
                "evidence": "SUPPORTED",
                "promoted_at": "2026-01-01T00:00:00Z",
                "promoted_by": "operator",
            }
        )
    )
    deployment = repo / "packages/production/extensions/deployments/example-family/deployment.yaml"
    deployment.parent.mkdir(parents=True)
    deployment.write_text(
        f"""schema_version: 2
strategy:
  family: example-family
  memory_version: v001
  preset: default
runtime:
  schedule: "*-*-* 00:00:00"
  timezone: UTC
  max_decision_age_seconds: 60
execution:
  venue: {venue}
  instruments:
    ASSET: EXAMPLE-PERP
"""
    )
    return repo, deployment


def _weights(decision: datetime) -> StrategyWeights:
    return StrategyWeights(
        weights=pl.DataFrame({"timestamp": [decision.replace(tzinfo=None)], "ASSET": [1.0], "CASH": [0.0]}),
        assets=["ASSET"],
        execution=ExecutionTiming.same_bar(
            rebalance_mode=RebalanceMode.FLAT_THEN_TARGET,
        ),
        observed_through=pl.Series([(decision - timedelta(minutes=1)).replace(tzinfo=None)]),
        metadata={"funding_since": 0},
    )


def _write_activation(state: Path, fingerprint: str) -> None:
    activation = state / "activations" / f"{fingerprint}.yaml"
    activation.parent.mkdir(parents=True)
    activation.write_text(
        f"""schema_version: 1
deployment_fingerprint: {fingerprint}
mode: live
account_id: account-1
max_position_notional_usd: "5"
max_order_notional_usd: "5"
expires_at: "2026-01-03T00:00:00Z"
enabled: true
"""
    )


def _arm(state: Path, fingerprint: str) -> None:
    path = state / "armed" / fingerprint
    path.parent.mkdir(parents=True)
    path.write_text("armed\n")


# --------------------------------------------------------------------------- #
# Runtime behavior
# --------------------------------------------------------------------------- #


def test_fingerprint_binds_canonical_final(tmp_path: Path) -> None:
    repo, deployment = _repository(tmp_path)
    before = deployment_fingerprint(deployment, repo)
    (repo / "db/strategies/example-family/versions/v001/final/meta.json").write_text(
        '{"selected_run_id":"different"}\n'
    )
    assert deployment_fingerprint(deployment, repo) != before


def test_dry_run_delegates_and_journals_without_live_authority(tmp_path: Path) -> None:
    ADAPTER_CALLS.clear()
    repo, deployment = _repository(tmp_path)
    state = tmp_path / "state"
    decision = datetime(2026, 1, 2, tzinfo=UTC)
    summary = run_once(
        deployment,
        repo,
        live=False,
        state_root=state,
        clock=lambda: decision,
        runner_factory=lambda definition: SimpleNamespace(decide=lambda: _weights(decision)),
    )
    assert summary["mode"] == "dry-run"
    assert summary["execution"] == {"trustworthy": True, "symbol": "EXAMPLE-PERP"}
    assert ADAPTER_CALLS[-1].live is False
    assert (state / "journals" / summary["deployment_fingerprint"] / "runs.jsonl").is_file()


def test_live_requires_activation_gate_and_arming_before_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, deployment = _repository(tmp_path)
    fingerprint = deployment_fingerprint(deployment, repo)
    state = tmp_path / "state"
    _write_activation(state, fingerprint)
    _arm(state, fingerprint)
    monkeypatch.setenv(HOST_GATE, "0")
    with pytest.raises(DeploymentValidationError, match=f"{HOST_GATE}=1"):
        run_once(
            deployment,
            repo,
            live=True,
            state_root=state,
            clock=lambda: datetime(2026, 1, 2, tzinfo=UTC),
            runner_factory=lambda definition: pytest.fail("strategy ran before authority"),
        )


def test_live_rechecks_authority_through_adapter_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ADAPTER_CALLS.clear()
    repo, deployment = _repository(tmp_path)
    fingerprint = deployment_fingerprint(deployment, repo)
    state = tmp_path / "state"
    _write_activation(state, fingerprint)
    _arm(state, fingerprint)
    monkeypatch.setenv(HOST_GATE, "1")
    decision = datetime(2026, 1, 2, tzinfo=UTC)
    summary = run_once(
        deployment,
        repo,
        live=True,
        state_root=state,
        clock=lambda: decision,
        runner_factory=lambda definition: SimpleNamespace(decide=lambda: _weights(decision)),
    )
    assert summary["mode"] == "live"
    assert ADAPTER_CALLS[-1].activation is not None


def test_state_root_inside_repository_is_rejected_before_strategy(tmp_path: Path) -> None:
    repo, deployment = _repository(tmp_path)
    with pytest.raises(DeploymentValidationError, match="must be outside the repository"):
        run_once(
            deployment,
            repo,
            live=False,
            state_root=repo / "runtime-state",
            clock=lambda: datetime(2026, 1, 2, tzinfo=UTC),
            runner_factory=lambda definition: pytest.fail("strategy ran for invalid state root"),
        )


def test_unknown_adapter_is_typed_and_stops_before_strategy(tmp_path: Path) -> None:
    repo, deployment = _repository(tmp_path, venue="missing-adapter")
    with pytest.raises(UnknownRuntimeAdapterError, match="missing-adapter"):
        run_once(
            deployment,
            repo,
            live=False,
            state_root=tmp_path / "state",
            clock=lambda: datetime(2026, 1, 2, tzinfo=UTC),
            runner_factory=lambda definition: pytest.fail("strategy ran without adapter"),
        )
