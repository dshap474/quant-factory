"""Deterministic registries for optional Production extension policy.

USAGE: extensions call ``register_runtime_adapter(...)`` from their loader entry point.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from production.contracts import (
    ACTIVATION_SCHEMA_VERSION,
    ActivationBinding,
    ActivationReceipt,
    DeploymentDefinition,
    DeploymentValidationError,
)

# --------------------------------------------------------------------------- #
# Errors and callback contracts
# --------------------------------------------------------------------------- #


class UnknownRuntimeAdapterError(DeploymentValidationError):
    """Raised when a deployment names an adapter the installed overlay lacks."""


class UnsupportedActivationSchemaError(DeploymentValidationError):
    """Raised when no installed parser owns an activation schema."""


ActivationParser = Callable[[Mapping[str, Any]], ActivationBinding]
ActivationCompatibility = Callable[[DeploymentDefinition, ActivationBinding], bool]
AuthorityRefresh = Callable[[], ActivationBinding]


@dataclass(frozen=True, slots=True)
class RuntimeExecutionContext:
    """Provider-neutral decision and authority facts passed to one adapter."""

    definition: DeploymentDefinition
    fingerprint: str
    runtime_state: Path
    activation: ActivationBinding | None
    weights: Any
    target_weight: Decimal
    symbol: str
    run_id: str
    target_id: str
    live: bool
    clock: Callable[[], datetime]
    executor_factory: Callable[..., Any] | None


@dataclass(frozen=True, slots=True)
class RuntimeExecutionResult:
    """Redacted adapter output for the generic runtime journal."""

    execution: Mapping[str, Any]
    capital: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAdapter:
    """Installed venue composition and its independent authority policy."""

    venue_id: str
    host_trading_gate: str
    dry_run_activation_required: bool
    activation_compatible: ActivationCompatibility
    execute: Callable[[RuntimeExecutionContext, AuthorityRefresh], RuntimeExecutionResult]


@dataclass(frozen=True, slots=True)
class FamilyPolicy:
    """Independent human-controlled capital gates for one installed family."""

    family_id: str
    capital_gates: tuple[str, ...]


# --------------------------------------------------------------------------- #
# Registries
# --------------------------------------------------------------------------- #

_RUNTIME_ADAPTERS: dict[str, RuntimeAdapter] = {}
_ACTIVATION_PARSERS: dict[int, ActivationParser] = {
    ACTIVATION_SCHEMA_VERSION: ActivationReceipt.from_mapping,
}
_FAMILY_POLICIES: dict[str, FamilyPolicy] = {}


def register_runtime_adapter(adapter: RuntimeAdapter) -> None:
    """Register one adapter, rejecting every duplicate venue ID."""
    if not adapter.venue_id or not adapter.host_trading_gate:
        raise DeploymentValidationError("runtime adapter requires non-empty venue and host gate IDs")
    if adapter.venue_id in _RUNTIME_ADAPTERS:
        raise DeploymentValidationError(f"duplicate runtime adapter ID: {adapter.venue_id}")
    _RUNTIME_ADAPTERS[adapter.venue_id] = adapter


def runtime_adapter(venue_id: str) -> RuntimeAdapter:
    """Return one installed adapter or the stable typed missing-adapter error."""
    try:
        return _RUNTIME_ADAPTERS[venue_id]
    except KeyError as exc:
        raise UnknownRuntimeAdapterError(f"unknown runtime adapter: {venue_id}") from exc


def register_activation_parser(schema_version: int, parser: ActivationParser) -> None:
    """Register one extension activation schema parser."""
    if schema_version <= 0:
        raise DeploymentValidationError("activation schema version must be positive")
    if schema_version in _ACTIVATION_PARSERS:
        raise DeploymentValidationError(f"duplicate activation parser ID: {schema_version}")
    _ACTIVATION_PARSERS[schema_version] = parser


def parse_activation_receipt(raw: Mapping[str, Any]) -> ActivationBinding:
    """Parse an activation through the built-in or installed extension registry."""
    schema_version = raw.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise DeploymentValidationError("activation.schema_version must be an integer")
    try:
        parser = _ACTIVATION_PARSERS[schema_version]
    except KeyError as exc:
        raise UnsupportedActivationSchemaError(f"unsupported activation.schema_version: {schema_version}") from exc
    return parser(raw)


def register_family_policy(policy: FamilyPolicy) -> None:
    """Register one family's independent capital-gate policy."""
    if not policy.family_id or any(not gate for gate in policy.capital_gates):
        raise DeploymentValidationError("family policy requires non-empty family and gate IDs")
    if policy.family_id in _FAMILY_POLICIES:
        raise DeploymentValidationError(f"duplicate family policy ID: {policy.family_id}")
    _FAMILY_POLICIES[policy.family_id] = policy


def family_policy(family_id: str) -> FamilyPolicy:
    """Return installed family policy or the neutral no-extra-gates default."""
    return _FAMILY_POLICIES.get(family_id, FamilyPolicy(family_id=family_id, capital_gates=()))


def _reset_registries_for_tests() -> None:
    """Restore the core-only registry state for isolated tests."""
    _RUNTIME_ADAPTERS.clear()
    _ACTIVATION_PARSERS.clear()
    _ACTIVATION_PARSERS[ACTIVATION_SCHEMA_VERSION] = ActivationReceipt.from_mapping
    _FAMILY_POLICIES.clear()


__all__ = [
    "ActivationCompatibility",
    "AuthorityRefresh",
    "FamilyPolicy",
    "RuntimeAdapter",
    "RuntimeExecutionContext",
    "RuntimeExecutionResult",
    "UnknownRuntimeAdapterError",
    "UnsupportedActivationSchemaError",
    "family_policy",
    "parse_activation_receipt",
    "register_activation_parser",
    "register_family_policy",
    "register_runtime_adapter",
    "runtime_adapter",
]
