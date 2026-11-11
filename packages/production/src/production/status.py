"""Read host-local deployment authority and runtime-journal facts.

Nothing in quant-factory runs on a timer: the operator runs each cycle by hand, so
``SCHEDULED`` and ``AUTONOMOUS_LIVE`` are always ``no`` and no service manager
is consulted.

USAGE: call ``production_status(deployment, repo_root, state_root)`` on the host.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from production.contracts import DeploymentValidationError
from production.deployment import deployment_fingerprint, validate_deployment
from production.extensions import load_production_extensions
from production.registry import family_policy, runtime_adapter
from production.state import (
    deactivation_record,
    find_activation_binding,
    is_armed,
    latest_journal_entry,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


# --------------------------------------------------------------------------- #
# Host readers
# --------------------------------------------------------------------------- #


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
    except OSError as exc:
        raise DeploymentValidationError(f"could not execute host reader {command[0]}") from exc


def _required_output(command: Sequence[str], run_command: _RunCommand) -> str:
    completed = run_command(command)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise DeploymentValidationError(f"could not read host state with {command[0]}: {detail}")
    return completed.stdout.strip()


def _git_sha(repo_root: Path, run_command: _RunCommand) -> str:
    sha = _required_output(
        ("git", "-c", f"safe.directory={repo_root}", "-C", str(repo_root), "rev-parse", "HEAD"),
        run_command,
    )
    if not _GIT_SHA_PATTERN.fullmatch(sha):
        raise DeploymentValidationError("host Git SHA is unreadable")
    return sha


def _last_journal(state_root: Path, fingerprint: str) -> str:
    payload = latest_journal_entry(state_root, fingerprint)
    if payload is None:
        return "never"
    decision_at = payload.get("decision_at")
    mode = payload.get("mode")
    if not isinstance(decision_at, str) or mode not in {"dry-run", "live"}:
        raise DeploymentValidationError("runtime journal has contradictory last-run facts")
    return f"{mode} {decision_at}"


# --------------------------------------------------------------------------- #
# Status composition
# --------------------------------------------------------------------------- #


def production_status(
    deployment: Path,
    repo_root: Path,
    state_root: Path,
    *,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
    run_command: _RunCommand = _run_command,
) -> tuple[tuple[str, str], ...]:
    """Return independent host facts followed by separately derived live booleans."""
    load_production_extensions()
    definition = validate_deployment(deployment, repo_root)
    fingerprint = deployment_fingerprint(deployment, repo_root)
    adapter = runtime_adapter(definition.execution.venue)

    activation = "missing"
    activation_expires = "n/a"
    activation_current = False
    receipt = find_activation_binding(state_root, fingerprint)
    receipt_exists = receipt is not None
    if receipt is not None:
        current_time = (now or datetime.now(tz=UTC)).astimezone(UTC)
        activation_expires = receipt.expires_at.isoformat()
        if not adapter.activation_compatible(definition, receipt):
            activation = "wrong-schema"
        elif not receipt.enabled:
            activation = "disabled"
        elif current_time >= receipt.expires_at:
            activation = "expired"
        else:
            activation = "enabled"
            activation_current = True

    armed = is_armed(state_root, fingerprint)
    deactivated = deactivation_record(state_root, fingerprint) is not None

    environment = environ if environ is not None else os.environ
    venue_open = environment.get(adapter.host_trading_gate) == "1"
    capital_gates = family_policy(definition.strategy.family).capital_gates
    capital_open = bool(capital_gates) and all(environment.get(gate) == "1" for gate in capital_gates)
    capital_approved = not capital_gates or capital_open
    can_trade = activation_current and armed and venue_open and capital_approved and not deactivated

    return (
        ("REGISTERED", "yes"),
        ("HOST_GIT_SHA", _git_sha(repo_root, run_command)),
        ("DEPLOYMENT_FINGERPRINT", fingerprint),
        ("ACTIVATION_RECEIPT", activation),
        ("ACTIVATION_EXPIRES_AT", activation_expires),
        ("ACTIVATION_CAPPED", "yes" if receipt_exists else "no"),
        ("ARMED", "yes" if armed else "no"),
        ("VENUE_GATE", "open" if venue_open else "closed"),
        ("CAPITAL_APPROVAL", "n/a" if not capital_gates else ("open" if capital_open else "closed")),
        ("DEACTIVATED", "yes" if deactivated else "no"),
        ("CAN_TRADE", "yes" if can_trade else "no"),
        ("SCHEDULED", "no"),
        ("AUTONOMOUS_LIVE", "no"),
        ("RUNTIME_JOURNAL", _last_journal(state_root, fingerprint)),
    )


__all__ = ["production_status"]
