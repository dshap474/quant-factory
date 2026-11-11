"""Provider-neutral one-shot strategy decision orchestration.

USAGE: call ``run_once(path, repo_root, live=False)`` with an installed adapter overlay.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from strategies.bootstrap import import_active_runner_modules

from production.contracts import ActivationBinding, DeploymentDefinition, DeploymentValidationError
from production.deployment import deployment_fingerprint, validate_deployment
from production.extensions import load_production_extensions
from production.registry import (
    RuntimeAdapter,
    RuntimeExecutionContext,
    family_policy,
    runtime_adapter,
)
from production.state import (
    append_journal,
    is_armed,
    load_activation,
    load_activation_binding,
    state_root_from_env,
    validate_state_root,
)
from strategies import StrategyRegistry

# --------------------------------------------------------------------------- #
# Runtime helpers
# --------------------------------------------------------------------------- #


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _runner(definition: Any) -> Any:
    import_active_runner_modules()
    runner_cls = StrategyRegistry.get(definition.strategy.family)
    return runner_cls.from_preset(
        definition.strategy.preset,
        save=False,
        memory_version=definition.strategy.memory_version,
    )


def _require_live_authority(
    definition: DeploymentDefinition,
    adapter: RuntimeAdapter,
    runtime_state: Path,
    fingerprint: str,
    *,
    now: datetime,
) -> ActivationBinding:
    """Load every installed external live gate at the point it is required."""
    activation = load_activation(runtime_state, fingerprint, now=now)
    if not adapter.activation_compatible(definition, activation):
        raise DeploymentValidationError("activation receipt is incompatible with runtime adapter")
    if os.environ.get(adapter.host_trading_gate) != "1":
        raise DeploymentValidationError(f"{adapter.host_trading_gate}=1 is required for live execution")
    for capital_gate in family_policy(definition.strategy.family).capital_gates:
        if os.environ.get(capital_gate) != "1":
            raise DeploymentValidationError(f"{capital_gate}=1 is required for live execution")
    if not is_armed(runtime_state, fingerprint):
        raise DeploymentValidationError("deployment is not independently armed")
    return activation


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


def run_once(
    deployment: Path,
    repo_root: Path,
    *,
    live: bool,
    state_root: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
    runner_factory: Callable[[Any], Any] | None = None,
    executor_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run one fresh decision through generic timing and installed adapter policy."""
    load_production_extensions()
    now_fn = clock or (lambda: datetime.now(tz=UTC))
    sleep_fn = sleeper or time.sleep
    now = _utc(now_fn())
    definition = validate_deployment(deployment, repo_root)
    fingerprint = deployment_fingerprint(deployment, repo_root)
    adapter = runtime_adapter(definition.execution.venue)
    runtime_state = validate_state_root(state_root or state_root_from_env(), repo_root)

    activation: ActivationBinding | None = None
    if live:
        activation = _require_live_authority(
            definition,
            adapter,
            runtime_state,
            fingerprint,
            now=now,
        )
    elif adapter.dry_run_activation_required:
        activation = load_activation_binding(runtime_state, fingerprint)
        if not adapter.activation_compatible(definition, activation):
            raise DeploymentValidationError("activation receipt is incompatible with runtime adapter")

    runner = (runner_factory or _runner)(definition)
    weights = runner.decide()
    now = _utc(now_fn())
    if len(weights.assets) != 1:
        raise DeploymentValidationError("live runtime currently supports exactly one traded asset")
    asset = weights.assets[0]
    latest = weights.weights.sort("timestamp").tail(1)
    decision_at = _utc(latest["timestamp"].item())
    age = (now - decision_at).total_seconds()
    if age < 0 or age > definition.runtime.max_decision_age_seconds:
        raise DeploymentValidationError(
            f"decision age {age:.3f}s exceeds [0, {definition.runtime.max_decision_age_seconds}]"
        )
    watermarks = weights.observed_through
    observed = None if watermarks is None else watermarks[weights.weights["timestamp"].arg_max()]
    if observed is None:
        raise DeploymentValidationError("strategy did not declare observed_through for its latest decision")
    observed_at = _utc(observed)
    if observed_at >= decision_at:
        raise DeploymentValidationError("strategy observed-through timestamp is not before the decision")
    symbol = definition.execution.instrument_for(asset)

    entry_at = decision_at + timedelta(seconds=weights.execution.entry_delay_seconds)
    if live and now < entry_at:
        sleep_fn((entry_at - now).total_seconds())
        now = _utc(now_fn())
    if live and now >= entry_at + timedelta(minutes=1):
        raise DeploymentValidationError("entry window was missed; catch-up execution is prohibited")
    if live:
        activation = _require_live_authority(
            definition,
            adapter,
            runtime_state,
            fingerprint,
            now=now,
        )

    target_weight = Decimal(str(latest[asset].item()))
    run_id = f"{decision_at.strftime('%Y%m%dT%H%M%SZ')}-{fingerprint[:12]}"
    target_id = f"{definition.strategy.family}-{definition.strategy.memory_version}-{decision_at.date().isoformat()}"
    context = RuntimeExecutionContext(
        definition=definition,
        fingerprint=fingerprint,
        runtime_state=runtime_state,
        activation=activation,
        weights=weights,
        target_weight=target_weight,
        symbol=symbol,
        run_id=run_id,
        target_id=target_id,
        live=live,
        clock=now_fn,
        executor_factory=executor_factory,
    )

    def refresh_authority() -> ActivationBinding:
        if not live:
            raise DeploymentValidationError("live authority refresh is unavailable during dry-run")
        return _require_live_authority(
            definition,
            adapter,
            runtime_state,
            fingerprint,
            now=_utc(now_fn()),
        )

    result = adapter.execute(context, refresh_authority)
    summary: dict[str, Any] = {
        "deployment_fingerprint": fingerprint,
        "family": definition.strategy.family,
        "memory_version": definition.strategy.memory_version,
        "decision_at": decision_at.isoformat(),
        "observed_through": observed_at.isoformat(),
        "mode": "live" if live else "dry-run",
        "execution": dict(result.execution),
    }
    if result.capital is not None:
        summary["capital"] = dict(result.capital)
    append_journal(runtime_state, fingerprint, summary)
    return summary


__all__ = ["run_once"]
