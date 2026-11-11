"""Static strategy deployment and external activation contracts.

USAGE: ``DeploymentDefinition.from_mapping(yaml.safe_load(text))``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

# --------------------------------------------------------------------------- #
# Constants and errors
# --------------------------------------------------------------------------- #

DEPLOYMENT_SCHEMA_VERSION = 2
ACTIVATION_SCHEMA_VERSION = 1
_FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MEMORY_VERSION_PATTERN = re.compile(r"^v\d{3}$")
_VENUE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class DeploymentValidationError(ValueError):
    """Raised when a deployment or activation violates its fail-closed contract."""


# --------------------------------------------------------------------------- #
# Deployment contracts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class StrategyReference:
    """Reference to a packaged strategy identity owned by strategies."""

    family: str
    memory_version: str
    preset: str


@dataclass(frozen=True, slots=True)
class RuntimeDefinition:
    """Cadence and decision freshness, never activation authority."""

    schedule: str
    timezone: str
    max_decision_age_seconds: int


@dataclass(frozen=True, slots=True)
class ExecutionDefinition:
    """Static venue and asset routing, never capital authority."""

    venue: str
    instruments: tuple[tuple[str, str], ...]

    def instrument_for(self, asset: str) -> str:
        try:
            return dict(self.instruments)[asset]
        except KeyError as exc:
            raise DeploymentValidationError(f"No execution instrument mapping for asset {asset!r}") from exc


@dataclass(frozen=True, slots=True)
class DeploymentDefinition:
    """Complete tracked definition for one strategy deployment bundle."""

    schema_version: int
    strategy: StrategyReference
    runtime: RuntimeDefinition
    execution: ExecutionDefinition

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DeploymentDefinition":
        _require_keys(raw, required={"schema_version", "strategy", "runtime", "execution"}, context="deployment")
        schema_version = _require_integer(raw["schema_version"], "schema_version")
        if schema_version != DEPLOYMENT_SCHEMA_VERSION:
            raise DeploymentValidationError(f"schema_version must be {DEPLOYMENT_SCHEMA_VERSION}, got {schema_version}")

        strategy_raw = _require_mapping(raw["strategy"], "strategy")
        _require_keys(strategy_raw, required={"family", "memory_version", "preset"}, context="strategy")
        strategy = StrategyReference(
            family=_require_string(strategy_raw["family"], "strategy.family"),
            memory_version=_require_string(strategy_raw["memory_version"], "strategy.memory_version"),
            preset=_require_string(strategy_raw["preset"], "strategy.preset"),
        )
        if not _FAMILY_PATTERN.fullmatch(strategy.family):
            raise DeploymentValidationError("strategy.family contains invalid characters")
        if not _MEMORY_VERSION_PATTERN.fullmatch(strategy.memory_version):
            raise DeploymentValidationError("strategy.memory_version must match vNNN")

        runtime_raw = _require_mapping(raw["runtime"], "runtime")
        _require_keys(
            runtime_raw,
            required={"schedule", "timezone", "max_decision_age_seconds"},
            context="runtime",
        )
        runtime = RuntimeDefinition(
            schedule=_require_string(runtime_raw["schedule"], "runtime.schedule"),
            timezone=_require_string(runtime_raw["timezone"], "runtime.timezone"),
            max_decision_age_seconds=_require_integer(
                runtime_raw["max_decision_age_seconds"], "runtime.max_decision_age_seconds"
            ),
        )
        if runtime.timezone != "UTC":
            raise DeploymentValidationError("runtime.timezone must be UTC")
        if runtime.max_decision_age_seconds < 1:
            raise DeploymentValidationError("runtime.max_decision_age_seconds must be positive")

        execution_raw = _require_mapping(raw["execution"], "execution")
        _require_keys(execution_raw, required={"venue", "instruments"}, context="execution")
        venue = _require_string(execution_raw["venue"], "execution.venue")
        if not _VENUE_PATTERN.fullmatch(venue):
            raise DeploymentValidationError("execution.venue contains invalid characters")
        instruments_raw = _require_mapping(execution_raw["instruments"], "execution.instruments")
        if not instruments_raw:
            raise DeploymentValidationError("execution.instruments must not be empty")
        instruments = tuple(
            sorted(
                (
                    _require_string(asset, "execution.instruments asset"),
                    _require_string(product, f"execution.instruments.{asset}"),
                )
                for asset, product in instruments_raw.items()
            )
        )
        return cls(
            schema_version=schema_version,
            strategy=strategy,
            runtime=runtime,
            execution=ExecutionDefinition(venue=venue, instruments=instruments),
        )


# --------------------------------------------------------------------------- #
# Activation contract
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ActivationReceipt:
    """External, expiring account and capital authority for one fingerprint."""

    schema_version: int
    deployment_fingerprint: str
    mode: str
    account_id: str
    max_position_notional_usd: Decimal
    max_order_notional_usd: Decimal
    expires_at: datetime
    enabled: bool
    execution_caps: Mapping[str, Decimal] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ActivationReceipt":
        caps = raw.get("execution_caps", {})
        _require_keys(
            {key: value for key, value in raw.items() if key != "execution_caps"},
            required={
                "schema_version",
                "deployment_fingerprint",
                "mode",
                "account_id",
                "max_position_notional_usd",
                "max_order_notional_usd",
                "expires_at",
                "enabled",
            },
            context="activation",
        )
        receipt = cls(
            schema_version=_require_integer(raw["schema_version"], "activation.schema_version"),
            deployment_fingerprint=_require_string(raw["deployment_fingerprint"], "activation.deployment_fingerprint"),
            mode=_require_string(raw["mode"], "activation.mode"),
            account_id=_require_string(raw["account_id"], "activation.account_id"),
            max_position_notional_usd=_require_decimal(
                raw["max_position_notional_usd"], "activation.max_position_notional_usd"
            ),
            max_order_notional_usd=_require_decimal(raw["max_order_notional_usd"], "activation.max_order_notional_usd"),
            expires_at=_require_utc_datetime(raw["expires_at"], "activation.expires_at"),
            enabled=_require_boolean(raw["enabled"], "activation.enabled"),
            execution_caps={
                name: _require_quoted_decimal(value, f"activation.execution_caps.{name}")
                for name, value in _require_mapping(caps, "activation.execution_caps").items()
            },
        )
        if receipt.schema_version != ACTIVATION_SCHEMA_VERSION:
            raise DeploymentValidationError(f"activation.schema_version must be {ACTIVATION_SCHEMA_VERSION}")
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.deployment_fingerprint):
            raise DeploymentValidationError("activation.deployment_fingerprint must be a SHA-256 hex digest")
        if receipt.mode != "live":
            raise DeploymentValidationError("activation.mode must be live")
        return receipt

    def validate_current(self, *, fingerprint: str, now: datetime) -> None:
        self.validate_binding(fingerprint=fingerprint)
        if not self.enabled:
            raise DeploymentValidationError("activation is disabled")
        if now.astimezone(UTC) >= self.expires_at:
            raise DeploymentValidationError("activation is expired")

    def validate_binding(self, *, fingerprint: str) -> None:
        """Validate account and cap binding without granting live authority."""
        if self.deployment_fingerprint != fingerprint:
            raise DeploymentValidationError("activation deployment fingerprint mismatch")

    def require_execution_cap(self, name: str) -> Decimal:
        """Return one venue-specific operator cap; absence fails closed (no default caps)."""
        if name not in self.execution_caps:
            raise DeploymentValidationError(f"activation.execution_caps.{name} is required for this venue")
        return self.execution_caps[name]


class ActivationBinding(Protocol):
    """Structural contract shared by built-in and extension activation receipts."""

    schema_version: int
    deployment_fingerprint: str
    expires_at: datetime
    enabled: bool

    def validate_current(self, *, fingerprint: str, now: datetime) -> None: ...

    def validate_binding(self, *, fingerprint: str) -> None: ...


# --------------------------------------------------------------------------- #
# Primitive validators
# --------------------------------------------------------------------------- #


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise DeploymentValidationError(f"{field} must be a string-keyed mapping")
    return value


def _require_keys(value: Mapping[str, Any], *, required: set[str], context: str) -> None:
    missing = required - set(value)
    unknown = set(value) - required
    if missing:
        raise DeploymentValidationError(f"{context} is missing required fields: {', '.join(sorted(missing))}")
    if unknown:
        raise DeploymentValidationError(f"{context} contains unknown fields: {', '.join(sorted(unknown))}")


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _require_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeploymentValidationError(f"{field} must be an integer")
    return value


def _require_boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise DeploymentValidationError(f"{field} must be a boolean")
    return value


def _require_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DeploymentValidationError(f"{field} must be a decimal") from exc
    if not result.is_finite() or result <= 0:
        raise DeploymentValidationError(f"{field} must be finite and positive")
    return result


def _require_quoted_decimal(value: Any, field: str) -> Decimal:
    if not isinstance(value, str):
        raise DeploymentValidationError(f"{field} must be a quoted decimal string")
    return _require_decimal(value, field)


def _require_utc_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise DeploymentValidationError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeploymentValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeploymentValidationError(f"{field} must include a UTC offset")
    return parsed.astimezone(UTC)


__all__ = [
    "ACTIVATION_SCHEMA_VERSION",
    "DEPLOYMENT_SCHEMA_VERSION",
    "ActivationBinding",
    "ActivationReceipt",
    "DeploymentDefinition",
    "DeploymentValidationError",
    "ExecutionDefinition",
    "RuntimeDefinition",
    "StrategyReference",
]
