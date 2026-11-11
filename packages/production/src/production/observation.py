"""Normalized, redacted production capital-observation contract.

Purpose: define the one durable record that a production host publishes for a
deployed strategy, plus the portfolio-membership manifest and the redaction
guard every published payload must survive.

A capital observation is *not* authority.  It records what an account was
observed to hold, what the deployment's independent authority facts were, and
which health checks were current.  Nothing here activates, arms, schedules, or
authorizes anything.

USAGE::

    observation = CapitalObservation(...)
    payload = observation.to_payload()
    assert_redacted(payload)
    manifest = load_portfolio_manifest(Path("packages/production/extensions/portfolio.yaml"))
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

from production.contracts import DeploymentValidationError

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

OBSERVATION_SCHEMA_VERSION = 1
PORTFOLIO_MANIFEST_SCHEMA_VERSION = 1

#: Every observation must carry exactly these independent checks.  A missing
#: check is a contract violation, not an implicit pass.
HEALTH_CHECK_NAMES: tuple[str, ...] = (
    "deployment_identity",
    "scheduler",
    "pipeline",
    "input_freshness",
    "execution",
    "account_snapshot",
    "reconciliation",
)
HEALTH_CHECK_STATES: frozenset[str] = frozenset({"passing", "failing", "unknown"})
OVERALL_HEALTH_STATES: tuple[str, ...] = ("healthy", "attention", "unknown", "paused")

ACTIVATION_STATES: frozenset[str] = frozenset({"missing", "disabled", "expired", "wrong-schema", "enabled"})
GATE_STATES: frozenset[str] = frozenset({"open", "closed", "n/a"})
POSITION_SIDES: frozenset[str] = frozenset({"LONG", "SHORT"})

_FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MEMORY_VERSION_PATTERN = re.compile(r"^v\d{3}$")
_ALIAS_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_PORTFOLIO_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VENUE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_INSTRUMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


# --------------------------------------------------------------------------- #
# Redaction guard
# --------------------------------------------------------------------------- #

#: Key fragments that may never appear in a published projection payload.
_FORBIDDEN_KEY_FRAGMENTS: tuple[str, ...] = (
    "account_id",
    "accountid",
    "api_key",
    "apikey",
    "credential",
    "passphrase",
    "password",
    "portfolio_uuid",
    "privatekey",
    "private_key",
    "receipt",
    "secret",
    "signature",
    "token",
    "uuid",
)
#: Keys whose value is allowed to be a long lowercase hex digest.
_HEX_DIGEST_ALLOWLIST: frozenset[str] = frozenset({"deployment_fingerprint", "host_git_sha"})
_UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_LONG_HEX_PATTERN = re.compile(r"^[0-9a-f]{32,}$")
_PEM_PATTERN = re.compile(r"-----BEGIN[ A-Z]*(PRIVATE KEY|CERTIFICATE)")


class RedactionError(DeploymentValidationError):
    """Raised when a payload would publish a forbidden fact."""


def assert_redacted(payload: Any, *, path: str = "$") -> None:
    """Fail closed when a payload carries a credential, raw identifier, or key.

    The observation dataclasses already restrict published fields structurally.
    This guard is the second, independent check: it runs over the serialized
    payload so a future field, a passthrough dict, or a hand-built projection
    cannot smuggle a secret into ``db/production``.
    """
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if not isinstance(key, str):
                raise RedactionError(f"{path}: projection keys must be strings")
            lowered = key.lower()
            for fragment in _FORBIDDEN_KEY_FRAGMENTS:
                if fragment in lowered:
                    raise RedactionError(f"{path}.{key}: forbidden key fragment {fragment!r}")
            assert_redacted(value, path=f"{path}.{key}")
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_redacted(value, path=f"{path}[{index}]")
        return
    if isinstance(payload, str):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if _PEM_PATTERN.search(payload):
            raise RedactionError(f"{path}: payload contains key material")
        if _UUID_PATTERN.search(payload):
            raise RedactionError(f"{path}: payload contains a raw identifier")
        if _LONG_HEX_PATTERN.match(payload) and leaf not in _HEX_DIGEST_ALLOWLIST:
            raise RedactionError(f"{path}: payload contains an unexpected hex digest")
        return
    if payload is None or isinstance(payload, (bool, int, float)):
        return
    raise RedactionError(f"{path}: unsupported projection value type {type(payload).__name__}")


# --------------------------------------------------------------------------- #
# Primitive validators
# --------------------------------------------------------------------------- #


def _require_pattern(value: Any, pattern: re.Pattern[str], field: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise DeploymentValidationError(f"{field} must match {pattern.pattern}")
    return value


def _require_alias(value: Any, field: str) -> str:
    """Require a human-chosen alias, never a raw provider identifier.

    The alias charset alone admits a bare UUID, so identifier shapes are
    rejected here rather than only at the redaction guard.
    """
    alias = _require_pattern(value, _ALIAS_PATTERN, field)
    if _UUID_PATTERN.fullmatch(alias) or _LONG_HEX_PATTERN.fullmatch(alias):
        raise DeploymentValidationError(f"{field} must be an alias, not an identifier")
    return alias


def _require_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise DeploymentValidationError(f"{field} must be a decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DeploymentValidationError(f"{field} must be a decimal") from exc
    if not result.is_finite():
        raise DeploymentValidationError(f"{field} must be finite")
    return result


def _optional_decimal(value: Any, field: str) -> Decimal | None:
    return None if value is None else _require_decimal(value, field)


def _require_utc(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise DeploymentValidationError(f"{field} must be timezone-aware UTC")
        return value.astimezone(UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DeploymentValidationError(f"{field} must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise DeploymentValidationError(f"{field} must include a UTC offset")
        return parsed.astimezone(UTC)
    raise DeploymentValidationError(f"{field} must be an ISO-8601 timestamp")


def _optional_utc(value: Any, field: str) -> datetime | None:
    return None if value is None else _require_utc(value, field)


def _number(value: Decimal | None) -> float | None:
    """Serialize a monetary decimal as a JSON number for API consumers."""
    return None if value is None else float(value)


# --------------------------------------------------------------------------- #
# Position, health, and authority records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PositionObservation:
    """One venue-reported position, priced at the observation timestamp."""

    instrument: str
    side: str
    quantity: Decimal
    contracts: int | None
    current_price: Decimal
    entry_price: Decimal
    market_value_usd: Decimal
    unrealized_pnl_usd: Decimal
    daily_realized_pnl_usd: Decimal | None

    def __post_init__(self) -> None:
        _require_pattern(self.instrument, _INSTRUMENT_PATTERN, "position.instrument")
        if self.side not in POSITION_SIDES:
            raise DeploymentValidationError("position.side must be LONG or SHORT")
        if self.contracts is not None and (isinstance(self.contracts, bool) or not isinstance(self.contracts, int)):
            raise DeploymentValidationError("position.contracts must be an integer or null")
        for name in ("quantity", "current_price", "entry_price", "market_value_usd", "unrealized_pnl_usd"):
            object.__setattr__(self, name, _require_decimal(getattr(self, name), f"position.{name}"))
        object.__setattr__(
            self,
            "daily_realized_pnl_usd",
            _optional_decimal(self.daily_realized_pnl_usd, "position.daily_realized_pnl_usd"),
        )

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready position record."""
        return {
            "instrument": self.instrument,
            "side": self.side,
            "quantity": _number(self.quantity),
            "contracts": self.contracts,
            "current_price": _number(self.current_price),
            "entry_price": _number(self.entry_price),
            "market_value_usd": _number(self.market_value_usd),
            "unrealized_pnl_usd": _number(self.unrealized_pnl_usd),
            "daily_realized_pnl_usd": _number(self.daily_realized_pnl_usd),
        }


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """One independent operational check with an explicit unknown state."""

    name: str
    state: str
    detail: str

    def __post_init__(self) -> None:
        if self.name not in HEALTH_CHECK_NAMES:
            raise DeploymentValidationError(f"unknown health check: {self.name}")
        if self.state not in HEALTH_CHECK_STATES:
            raise DeploymentValidationError(f"health check state must be one of {sorted(HEALTH_CHECK_STATES)}")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise DeploymentValidationError("health check detail must be a non-empty string")

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready check record."""
        return {"name": self.name, "state": self.state, "detail": self.detail}


def require_complete_health_checks(checks: Sequence[HealthCheck]) -> tuple[HealthCheck, ...]:
    """Require exactly one record per declared check, in declaration order."""
    by_name = {}
    for check in checks:
        if not isinstance(check, HealthCheck):
            raise DeploymentValidationError("health_checks must contain HealthCheck values")
        if check.name in by_name:
            raise DeploymentValidationError(f"duplicate health check: {check.name}")
        by_name[check.name] = check
    missing = [name for name in HEALTH_CHECK_NAMES if name not in by_name]
    if missing:
        raise DeploymentValidationError(f"health_checks is missing: {', '.join(missing)}")
    return tuple(by_name[name] for name in HEALTH_CHECK_NAMES)


@dataclass(frozen=True, slots=True)
class AuthorityFacts:
    """Independent lifecycle and authority facts, never a health verdict."""

    activation_state: str
    activation_expires_at: datetime | None
    armed: bool
    venue_gate: str
    capital_gate: str
    deactivated: bool
    can_trade: bool
    scheduled: bool
    autonomous_live: bool

    def __post_init__(self) -> None:
        if self.activation_state not in ACTIVATION_STATES:
            raise DeploymentValidationError(f"activation_state must be one of {sorted(ACTIVATION_STATES)}")
        for name in ("venue_gate", "capital_gate"):
            if getattr(self, name) not in GATE_STATES:
                raise DeploymentValidationError(f"{name} must be one of {sorted(GATE_STATES)}")
        for name in ("armed", "deactivated", "can_trade", "scheduled", "autonomous_live"):
            if not isinstance(getattr(self, name), bool):
                raise DeploymentValidationError(f"{name} must be a boolean")
        object.__setattr__(
            self,
            "activation_expires_at",
            _optional_utc(self.activation_expires_at, "activation_expires_at"),
        )
        if self.autonomous_live and not (self.can_trade and self.scheduled):
            raise DeploymentValidationError("autonomous_live contradicts can_trade and scheduled")

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready authority record."""
        return {
            "activation_state": self.activation_state,
            "activation_expires_at": (
                None if self.activation_expires_at is None else self.activation_expires_at.isoformat()
            ),
            "armed": self.armed,
            "venue_gate": self.venue_gate,
            "capital_gate": self.capital_gate,
            "deactivated": self.deactivated,
            "can_trade": self.can_trade,
            "scheduled": self.scheduled,
            "autonomous_live": self.autonomous_live,
        }


@dataclass(frozen=True, slots=True)
class LastRun:
    """Latest production-cycle and runtime-journal facts."""

    result: str
    at: datetime | None
    mode: str | None
    journal_at: datetime | None

    def __post_init__(self) -> None:
        if self.result not in {"never", "success", "failure"}:
            raise DeploymentValidationError("last_run.result must be never, success, or failure")
        if self.mode is not None and self.mode not in {"dry-run", "live"}:
            raise DeploymentValidationError("last_run.mode must be dry-run, live, or null")
        object.__setattr__(self, "at", _optional_utc(self.at, "last_run.at"))
        object.__setattr__(self, "journal_at", _optional_utc(self.journal_at, "last_run.journal_at"))
        if self.result == "never" and self.at is not None:
            raise DeploymentValidationError("last_run.at contradicts result never")

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready last-run record."""
        return {
            "result": self.result,
            "at": None if self.at is None else self.at.isoformat(),
            "mode": self.mode,
            "journal_at": None if self.journal_at is None else self.journal_at.isoformat(),
        }


# --------------------------------------------------------------------------- #
# Capital observation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CapitalObservation:
    """One normalized, redacted capital observation for one portfolio member.

    ``external_flow_usd_since_previous`` is the net operator cash movement
    between the previous observation for this same member and this one.  It is
    signed: a deposit is positive, a withdrawal negative.  Period P&L is never
    the raw equity difference; see ``production.aggregation.period_pnl``.
    """

    portfolio_id: str
    family: str
    memory_version: str
    deployment_fingerprint: str
    observed_at: datetime
    venue: str
    account_alias: str
    host_alias: str
    equity_usd: Decimal
    cash_usd: Decimal | None
    gross_exposure_usd: Decimal | None
    net_exposure_usd: Decimal | None
    external_flow_usd_since_previous: Decimal
    realized_pnl_usd: Decimal | None
    unrealized_pnl_usd: Decimal | None
    fees_usd: Decimal | None
    funding_pnl_usd: Decimal | None
    positions: tuple[PositionObservation, ...]
    health_checks: tuple[HealthCheck, ...]
    authority_facts: AuthorityFacts
    last_run: LastRun
    schema_version: int = OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVATION_SCHEMA_VERSION:
            raise DeploymentValidationError(f"schema_version must be {OBSERVATION_SCHEMA_VERSION}")
        _require_pattern(self.portfolio_id, _PORTFOLIO_ID_PATTERN, "portfolio_id")
        _require_pattern(self.family, _FAMILY_PATTERN, "family")
        _require_pattern(self.memory_version, _MEMORY_VERSION_PATTERN, "memory_version")
        _require_pattern(self.deployment_fingerprint, _FINGERPRINT_PATTERN, "deployment_fingerprint")
        _require_pattern(self.venue, _VENUE_PATTERN, "venue")
        _require_alias(self.account_alias, "account_alias")
        _require_alias(self.host_alias, "host_alias")
        object.__setattr__(self, "observed_at", _require_utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "equity_usd", _require_decimal(self.equity_usd, "equity_usd"))
        object.__setattr__(
            self,
            "external_flow_usd_since_previous",
            _require_decimal(self.external_flow_usd_since_previous, "external_flow_usd_since_previous"),
        )
        for name in (
            "cash_usd",
            "gross_exposure_usd",
            "net_exposure_usd",
            "realized_pnl_usd",
            "unrealized_pnl_usd",
            "fees_usd",
            "funding_pnl_usd",
        ):
            object.__setattr__(self, name, _optional_decimal(getattr(self, name), name))
        positions = tuple(self.positions)
        if any(not isinstance(position, PositionObservation) for position in positions):
            raise DeploymentValidationError("positions must contain PositionObservation values")
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "health_checks", require_complete_health_checks(self.health_checks))
        if not isinstance(self.authority_facts, AuthorityFacts):
            raise DeploymentValidationError("authority_facts must be AuthorityFacts")
        if not isinstance(self.last_run, LastRun):
            raise DeploymentValidationError("last_run must be LastRun")

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready, redaction-checked observation record."""
        payload = {
            "schema_version": self.schema_version,
            "portfolio_id": self.portfolio_id,
            "family": self.family,
            "memory_version": self.memory_version,
            "deployment_fingerprint": self.deployment_fingerprint,
            "observed_at": self.observed_at.isoformat(),
            "venue": self.venue,
            "account_alias": self.account_alias,
            "host_alias": self.host_alias,
            "equity_usd": _number(self.equity_usd),
            "cash_usd": _number(self.cash_usd),
            "gross_exposure_usd": _number(self.gross_exposure_usd),
            "net_exposure_usd": _number(self.net_exposure_usd),
            "external_flow_usd_since_previous": _number(self.external_flow_usd_since_previous),
            "realized_pnl_usd": _number(self.realized_pnl_usd),
            "unrealized_pnl_usd": _number(self.unrealized_pnl_usd),
            "fees_usd": _number(self.fees_usd),
            "funding_pnl_usd": _number(self.funding_pnl_usd),
            "positions": [position.to_payload() for position in self.positions],
            "health_checks": [check.to_payload() for check in self.health_checks],
            "authority_facts": self.authority_facts.to_payload(),
            "last_run": self.last_run.to_payload(),
        }
        assert_redacted(payload)
        return payload

    @classmethod
    def from_payload(cls, raw: Mapping[str, Any]) -> "CapitalObservation":
        """Rebuild one observation from its published record."""
        if not isinstance(raw, Mapping):
            raise DeploymentValidationError("observation record must be a mapping")
        authority = raw.get("authority_facts")
        if not isinstance(authority, Mapping):
            raise DeploymentValidationError("observation.authority_facts must be a mapping")
        last_run = raw.get("last_run")
        if not isinstance(last_run, Mapping):
            raise DeploymentValidationError("observation.last_run must be a mapping")
        positions_raw = raw.get("positions") or []
        checks_raw = raw.get("health_checks") or []
        if not isinstance(positions_raw, Sequence) or isinstance(positions_raw, (str, bytes)):
            raise DeploymentValidationError("observation.positions must be a list")
        if not isinstance(checks_raw, Sequence) or isinstance(checks_raw, (str, bytes)):
            raise DeploymentValidationError("observation.health_checks must be a list")
        return cls(
            schema_version=raw.get("schema_version", 0),
            portfolio_id=raw.get("portfolio_id", ""),
            family=raw.get("family", ""),
            memory_version=raw.get("memory_version", ""),
            deployment_fingerprint=raw.get("deployment_fingerprint", ""),
            observed_at=cast(datetime, raw.get("observed_at")),
            venue=raw.get("venue", ""),
            account_alias=raw.get("account_alias", ""),
            host_alias=raw.get("host_alias", ""),
            equity_usd=cast(Decimal, raw.get("equity_usd")),
            cash_usd=raw.get("cash_usd"),
            gross_exposure_usd=raw.get("gross_exposure_usd"),
            net_exposure_usd=raw.get("net_exposure_usd"),
            external_flow_usd_since_previous=raw.get("external_flow_usd_since_previous", 0),
            realized_pnl_usd=raw.get("realized_pnl_usd"),
            unrealized_pnl_usd=raw.get("unrealized_pnl_usd"),
            fees_usd=raw.get("fees_usd"),
            funding_pnl_usd=raw.get("funding_pnl_usd"),
            positions=tuple(
                PositionObservation(
                    instrument=position.get("instrument", ""),
                    side=position.get("side", ""),
                    quantity=position.get("quantity"),
                    contracts=position.get("contracts"),
                    current_price=position.get("current_price"),
                    entry_price=position.get("entry_price"),
                    market_value_usd=position.get("market_value_usd"),
                    unrealized_pnl_usd=position.get("unrealized_pnl_usd"),
                    daily_realized_pnl_usd=position.get("daily_realized_pnl_usd"),
                )
                for position in positions_raw
                if isinstance(position, Mapping)
            ),
            health_checks=tuple(
                HealthCheck(
                    name=check.get("name", ""),
                    state=check.get("state", ""),
                    detail=check.get("detail", ""),
                )
                for check in checks_raw
                if isinstance(check, Mapping)
            ),
            authority_facts=AuthorityFacts(
                activation_state=authority.get("activation_state", ""),
                activation_expires_at=authority.get("activation_expires_at"),
                armed=authority.get("armed", False),
                venue_gate=authority.get("venue_gate", ""),
                capital_gate=authority.get("capital_gate", ""),
                deactivated=authority.get("deactivated", False),
                can_trade=authority.get("can_trade", False),
                scheduled=authority.get("scheduled", False),
                autonomous_live=authority.get("autonomous_live", False),
            ),
            last_run=LastRun(
                result=last_run.get("result", ""),
                at=last_run.get("at"),
                mode=last_run.get("mode"),
                journal_at=last_run.get("journal_at"),
            ),
        )


# --------------------------------------------------------------------------- #
# Derived lifecycle and health
# --------------------------------------------------------------------------- #


def lifecycle_state(authority: AuthorityFacts) -> str:
    """Return the deployment's lifecycle state, never a health verdict."""
    if authority.deactivated:
        return "deactivated"
    if authority.autonomous_live:
        return "autonomous-live"
    if authority.can_trade:
        return "authorized"
    if authority.activation_state == "enabled":
        return "activated"
    if authority.activation_state in {"disabled", "expired", "wrong-schema"}:
        return f"activation-{authority.activation_state}"
    return "registered"


def overall_health(checks: Sequence[HealthCheck], authority: AuthorityFacts) -> str:
    """Roll independent checks up without turning intent into failure.

    Deactivation is an intentional lifecycle state and reports ``paused``.  A
    check that has nothing to judge yet reports ``unknown`` rather than passing.
    """
    if authority.deactivated:
        return "paused"
    states = {check.state for check in require_complete_health_checks(checks)}
    if "failing" in states:
        return "attention"
    if "unknown" in states:
        return "unknown"
    return "healthy"


# --------------------------------------------------------------------------- #
# Portfolio membership manifest
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PortfolioMember:
    """Explicit, non-authority membership declaration for one family."""

    family: str
    included: bool
    account_snapshot_max_age_seconds: int

    def __post_init__(self) -> None:
        _require_pattern(self.family, _FAMILY_PATTERN, "member.family")
        if not isinstance(self.included, bool):
            raise DeploymentValidationError("member.included must be a boolean")
        if isinstance(self.account_snapshot_max_age_seconds, bool) or not isinstance(
            self.account_snapshot_max_age_seconds, int
        ):
            raise DeploymentValidationError("member.account_snapshot_max_age_seconds must be an integer")
        if self.account_snapshot_max_age_seconds < 1:
            raise DeploymentValidationError("member.account_snapshot_max_age_seconds must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioManifest:
    """Explicit portfolio identity and membership.

    Membership is declared here and nowhere else.  ``CAN_TRADE=yes``, the
    presence of a deployment file, and a nonzero position are all insufficient:
    a strategy is in the portfolio only when this manifest says so. An empty
    membership list represents a portfolio with no current strategies.
    """

    schema_version: int
    portfolio_id: str
    members: tuple[PortfolioMember, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PORTFOLIO_MANIFEST_SCHEMA_VERSION:
            raise DeploymentValidationError(f"portfolio schema_version must be {PORTFOLIO_MANIFEST_SCHEMA_VERSION}")
        _require_pattern(self.portfolio_id, _PORTFOLIO_ID_PATTERN, "portfolio_id")
        members = tuple(self.members)
        families = [member.family for member in members]
        if len(set(families)) != len(families):
            raise DeploymentValidationError("portfolio members must be unique by family")
        object.__setattr__(self, "members", members)

    @property
    def included_members(self) -> tuple[PortfolioMember, ...]:
        """Return only the members whose data the aggregate must contain."""
        return tuple(member for member in self.members if member.included)

    def member(self, family: str) -> PortfolioMember:
        """Return one declared member, failing closed on an unknown family."""
        for candidate in self.members:
            if candidate.family == family:
                return candidate
        raise DeploymentValidationError(f"family is not a declared portfolio member: {family}")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PortfolioManifest":
        """Parse the manifest document with no implicit defaults on identity."""
        if not isinstance(raw, Mapping):
            raise DeploymentValidationError("portfolio manifest must contain a mapping")
        unknown = set(raw) - {"schema_version", "portfolio_id", "members"}
        if unknown:
            raise DeploymentValidationError(f"portfolio manifest has unknown fields: {', '.join(sorted(unknown))}")
        members_raw = raw.get("members")
        if not isinstance(members_raw, Sequence) or isinstance(members_raw, (str, bytes)):
            raise DeploymentValidationError("portfolio.members must be a list")
        members = []
        for entry in members_raw:
            if not isinstance(entry, Mapping):
                raise DeploymentValidationError("portfolio.members entries must be mappings")
            unknown_member = set(entry) - {"family", "included", "account_snapshot_max_age_seconds"}
            if unknown_member:
                raise DeploymentValidationError(
                    f"portfolio member has unknown fields: {', '.join(sorted(unknown_member))}"
                )
            members.append(
                PortfolioMember(
                    family=entry.get("family", ""),
                    included=entry.get("included", False),
                    account_snapshot_max_age_seconds=entry.get("account_snapshot_max_age_seconds", 0),
                )
            )
        return cls(
            schema_version=raw.get("schema_version", 0),
            portfolio_id=raw.get("portfolio_id", ""),
            members=tuple(members),
        )


def load_portfolio_manifest(path: Path) -> PortfolioManifest:
    """Load the tracked, non-authority portfolio-membership manifest."""
    resolved = path.resolve()
    if not resolved.is_file():
        raise DeploymentValidationError(f"portfolio manifest does not exist: {resolved}")
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeploymentValidationError(f"could not read portfolio manifest: {resolved}") from exc
    return PortfolioManifest.from_mapping(raw)


__all__ = [
    "ACTIVATION_STATES",
    "HEALTH_CHECK_NAMES",
    "HEALTH_CHECK_STATES",
    "OBSERVATION_SCHEMA_VERSION",
    "OVERALL_HEALTH_STATES",
    "PORTFOLIO_MANIFEST_SCHEMA_VERSION",
    "AuthorityFacts",
    "CapitalObservation",
    "HealthCheck",
    "LastRun",
    "PortfolioManifest",
    "PortfolioMember",
    "PositionObservation",
    "RedactionError",
    "assert_redacted",
    "lifecycle_state",
    "load_portfolio_manifest",
    "overall_health",
    "require_complete_health_checks",
]
