"""Publish the read-only production telemetry projection under ``db/production``.

Purpose: turn host-local truth — the validated deployment, the independent
status facts, and the redacted capital history already recorded in the runtime
journal — into the append-only, credential-free projection that the read-only
DB API serves.

The publisher runs on the production host.  It never calls a venue: capital
facts reach it only through journal entries written by a cycle that already
authenticated.  The DB API, in turn, never reads the state root, never resolves
a credential, and never calls a venue.

Layout::

    db/production/overview.json                          (atomically replaced)
    db/production/strategies/<family>/snapshot.json       (atomically replaced)
    db/production/strategies/<family>/observations.jsonl  (append-only)
    db/production/strategies/<family>/runs.jsonl          (append-only)

USAGE::

    publish_projection(
        db_root=Path("db"),
        manifest=load_portfolio_manifest(Path("packages/production/extensions/portfolio.yaml")),
        strategies=[strategy_projection(...)],
        now=datetime.now(tz=UTC),
    )
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from production.aggregation import (
    AggregatePoint,
    PerformanceMetrics,
    SeriesPoint,
    StrategySeries,
    aggregate_series,
    performance_metrics,
    strategy_series,
)
from production.contracts import DeploymentDefinition, DeploymentValidationError
from production.observation import (
    HEALTH_CHECK_NAMES,
    AuthorityFacts,
    CapitalObservation,
    HealthCheck,
    LastRun,
    PortfolioManifest,
    PositionObservation,
    assert_redacted,
    lifecycle_state,
    overall_health,
)
from production.state import journal_entries

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

PROJECTION_SCHEMA_VERSION = 1
PROJECTION_DIR = "production"
OVERVIEW_FILE = "overview.json"
STRATEGIES_DIR = "strategies"
SNAPSHOT_FILE = "snapshot.json"
OBSERVATIONS_FILE = "observations.jsonl"
RUNS_FILE = "runs.jsonl"

#: Bound on any file this module reads back before appending.
_MAX_READ_BYTES = 8 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Host fact decoding
# --------------------------------------------------------------------------- #


def host_facts(status: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Index ``production_status`` output by fact name."""
    facts: dict[str, str] = {}
    for name, value in status:
        if name in facts:
            raise DeploymentValidationError(f"duplicate host fact: {name}")
        facts[name] = value
    return facts


def _yes(facts: Mapping[str, str], name: str) -> bool:
    value = facts.get(name)
    if value not in {"yes", "no"}:
        raise DeploymentValidationError(f"host fact {name} must be yes or no")
    return value == "yes"


def _split_last_run(value: str) -> tuple[str, str | None]:
    if value == "never":
        return "never", None
    result, _, timestamp = value.partition(" ")
    if result not in {"success", "failure"} or not timestamp:
        raise DeploymentValidationError("host fact LAST_RUN is contradictory")
    return result, timestamp


def _split_journal(value: str) -> tuple[str | None, str | None]:
    if value == "never":
        return None, None
    mode, _, timestamp = value.partition(" ")
    if mode not in {"dry-run", "live"} or not timestamp:
        raise DeploymentValidationError("host fact RUNTIME_JOURNAL is contradictory")
    return mode, timestamp


def authority_from_host(facts: Mapping[str, str]) -> AuthorityFacts:
    """Read the independent authority facts, keeping every state separate."""
    expires = facts.get("ACTIVATION_EXPIRES_AT", "n/a")
    return AuthorityFacts(
        activation_state=facts.get("ACTIVATION_RECEIPT", "missing"),
        activation_expires_at=cast(datetime | None, None if expires == "n/a" else expires),
        armed=_yes(facts, "ARMED"),
        venue_gate=facts.get("VENUE_GATE", "closed"),
        capital_gate=facts.get("CAPITAL_APPROVAL", "closed"),
        deactivated=_yes(facts, "DEACTIVATED"),
        can_trade=_yes(facts, "CAN_TRADE"),
        scheduled=_yes(facts, "SCHEDULED"),
        autonomous_live=_yes(facts, "AUTONOMOUS_LIVE"),
    )


def last_run_from_host(facts: Mapping[str, str]) -> LastRun:
    """Read the last production-cycle and runtime-journal facts."""
    result, at = _split_last_run(facts.get("LAST_RUN", "never"))
    mode, journal_at = _split_journal(facts.get("RUNTIME_JOURNAL", "never"))
    return LastRun(
        result=result,
        at=cast(datetime | None, at),
        mode=mode,
        journal_at=cast(datetime | None, journal_at),
    )


def health_checks_from_host(
    facts: Mapping[str, str],
    *,
    expected_fingerprint: str,
    capital_as_of: datetime | None,
    execution_trustworthy: bool | None,
    reconciled: bool | None,
    now: datetime,
    max_age_seconds: int,
) -> tuple[HealthCheck, ...]:
    """Derive the seven independent checks without turning intent into failure.

    A closed gate or a disabled activation is lifecycle or authority state.
    Nothing runs on a timer, so the scheduler check is always ``unknown``.
    Where a check has nothing to judge it reports ``unknown`` rather than
    passing.
    """
    checks: list[HealthCheck] = []

    fingerprint = facts.get("DEPLOYMENT_FINGERPRINT", "")
    if fingerprint == expected_fingerprint:
        checks.append(
            HealthCheck(
                name="deployment_identity",
                state="passing",
                detail="host fingerprint matches the packaged deployment",
            )
        )
    else:
        checks.append(
            HealthCheck(
                name="deployment_identity",
                state="failing",
                detail="host fingerprint does not match the packaged deployment",
            )
        )

    checks.append(
        HealthCheck(
            name="scheduler",
            state="unknown",
            detail="no timer; the operator runs each cycle by hand",
        )
    )

    result, at = _split_last_run(facts.get("LAST_RUN", "never"))
    if result == "never":
        checks.append(
            HealthCheck(name="pipeline", state="unknown", detail="no cycle result is recorded; cycles are run by hand")
        )
    elif result == "success":
        checks.append(HealthCheck(name="pipeline", state="passing", detail=f"last cycle succeeded at {at}"))
    else:
        checks.append(HealthCheck(name="pipeline", state="failing", detail=f"last cycle failed at {at}"))

    mode, journal_at = _split_journal(facts.get("RUNTIME_JOURNAL", "never"))
    if journal_at is None:
        checks.append(HealthCheck(name="input_freshness", state="unknown", detail="no decision has been journaled"))
    else:
        decision_at = datetime.fromisoformat(journal_at.replace("Z", "+00:00"))
        age = now.astimezone(UTC) - decision_at.astimezone(UTC)
        if age <= timedelta(seconds=max_age_seconds):
            checks.append(
                HealthCheck(
                    name="input_freshness",
                    state="passing",
                    detail=f"latest decision at {journal_at}",
                )
            )
        else:
            checks.append(
                HealthCheck(
                    name="input_freshness",
                    state="failing",
                    detail=f"latest decision at {journal_at} is older than the allowed window",
                )
            )

    if execution_trustworthy is None:
        checks.append(HealthCheck(name="execution", state="unknown", detail="no execution has been journaled"))
    elif execution_trustworthy:
        checks.append(HealthCheck(name="execution", state="passing", detail=f"latest {mode} execution resolved"))
    else:
        checks.append(
            HealthCheck(
                name="execution",
                state="failing",
                detail="latest execution did not resolve to a trustworthy terminal state",
            )
        )

    if capital_as_of is None:
        checks.append(
            HealthCheck(
                name="account_snapshot",
                state="unknown",
                detail="no account snapshot has been observed",
            )
        )
    elif now.astimezone(UTC) - capital_as_of > timedelta(seconds=max_age_seconds):
        checks.append(
            HealthCheck(
                name="account_snapshot",
                state="failing",
                detail=f"account snapshot from {capital_as_of.isoformat()} is stale",
            )
        )
    else:
        checks.append(
            HealthCheck(
                name="account_snapshot",
                state="passing",
                detail=f"account snapshot as of {capital_as_of.isoformat()}",
            )
        )

    if reconciled is None:
        checks.append(
            HealthCheck(
                name="reconciliation",
                state="unknown",
                detail="no execution and snapshot pair to reconcile",
            )
        )
    elif reconciled:
        checks.append(
            HealthCheck(
                name="reconciliation",
                state="passing",
                detail="venue position matches the last executed target",
            )
        )
    else:
        checks.append(
            HealthCheck(
                name="reconciliation",
                state="failing",
                detail="venue position does not match the last executed target",
            )
        )

    ordered = {check.name: check for check in checks}
    return tuple(ordered[name] for name in HEALTH_CHECK_NAMES)


# --------------------------------------------------------------------------- #
# External cash flows
# --------------------------------------------------------------------------- #


def flows_path(state_root: Path, fingerprint: str) -> Path:
    """Return the operator-maintained external cash-flow ledger path."""
    return state_root / "flows" / fingerprint / "flows.jsonl"


def read_flows(path: Path) -> tuple[tuple[datetime, Decimal], ...]:
    """Read the signed external cash-flow ledger, oldest first.

    Each line is ``{"at": <ISO-8601 UTC>, "amount_usd": <signed decimal>}``.
    Deposits are positive and withdrawals negative.  Without this ledger a
    deposit would masquerade as profit, so an unreadable ledger fails closed
    rather than defaulting to zero.
    """
    text = _read_text(path, missing_ok=True)
    if text is None:
        return ()
    entries: list[tuple[datetime, Decimal]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DeploymentValidationError(f"cash-flow ledger is unreadable: {path}") from exc
        if not isinstance(payload, Mapping):
            raise DeploymentValidationError(f"cash-flow ledger is unreadable: {path}")
        at = payload.get("at")
        amount = payload.get("amount_usd")
        if not isinstance(at, str):
            raise DeploymentValidationError(f"cash-flow entry is missing a timestamp: {path}")
        try:
            when = datetime.fromisoformat(at.replace("Z", "+00:00"))
            value = Decimal(str(amount))
        except (ValueError, InvalidOperation) as exc:
            raise DeploymentValidationError(f"cash-flow entry is unreadable: {path}") from exc
        if when.tzinfo is None or not value.is_finite():
            raise DeploymentValidationError(f"cash-flow entry is unreadable: {path}")
        entries.append((when.astimezone(UTC), value))
    return tuple(sorted(entries, key=lambda item: item[0]))


def _flow_between(
    flows: Sequence[tuple[datetime, Decimal]],
    previous: datetime | None,
    current: datetime,
) -> Decimal:
    """Sum flows in ``(previous, current]``; flows at or before inception fund it."""
    if previous is None:
        return Decimal("0")
    return sum((amount for when, amount in flows if previous < when <= current), start=Decimal("0"))


# --------------------------------------------------------------------------- #
# Observation construction
# --------------------------------------------------------------------------- #


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DeploymentValidationError(f"journal capital {field} is unreadable") from exc
    if not result.is_finite():
        raise DeploymentValidationError(f"journal capital {field} is unreadable")
    return result


def _positions(raw: Any) -> tuple[PositionObservation, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise DeploymentValidationError("journal capital positions are unreadable")
    return tuple(
        PositionObservation(
            instrument=item.get("instrument", ""),
            side=item.get("side", ""),
            quantity=_decimal(item.get("quantity"), "quantity"),
            contracts=item.get("contracts"),
            current_price=_decimal(item.get("current_price"), "current_price"),
            entry_price=_decimal(item.get("entry_price"), "entry_price"),
            market_value_usd=_decimal(item.get("market_value_usd"), "market_value_usd"),
            unrealized_pnl_usd=_decimal(item.get("unrealized_pnl_usd"), "unrealized_pnl_usd"),
            daily_realized_pnl_usd=(
                None
                if item.get("daily_realized_pnl_usd") is None
                else _decimal(item.get("daily_realized_pnl_usd"), "daily_realized_pnl_usd")
            ),
        )
        for item in raw
        if isinstance(item, Mapping)
    )


@dataclass(frozen=True, slots=True)
class JournalRecord:
    """One redacted runtime-journal entry, decoded for projection use."""

    decision_at: datetime
    mode: str
    capital: Mapping[str, Any] | None
    execution: Mapping[str, Any]

    @property
    def trustworthy(self) -> bool | None:
        """Return whether the execution resolved, if the entry says."""
        value = self.execution.get("trustworthy")
        return value if isinstance(value, bool) else None

    @property
    def reconciled(self) -> bool | None:
        """Return whether the venue ended at the executed target."""
        target = self.execution.get("target_contracts")
        final = self.execution.get("final_contracts")
        if not isinstance(target, int) or not isinstance(final, int):
            return None
        return target == final


def decode_journal(entries: Sequence[Mapping[str, Any]]) -> tuple[JournalRecord, ...]:
    """Decode runtime-journal entries into ordered, typed records."""
    records: list[JournalRecord] = []
    for entry in entries:
        decision_at = entry.get("decision_at")
        mode = entry.get("mode")
        execution = entry.get("execution")
        if not isinstance(decision_at, str) or mode not in {"dry-run", "live"}:
            raise DeploymentValidationError("runtime journal entry is contradictory")
        if not isinstance(execution, Mapping):
            raise DeploymentValidationError("runtime journal entry is missing execution facts")
        capital = entry.get("capital")
        if capital is not None and not isinstance(capital, Mapping):
            raise DeploymentValidationError("runtime journal capital facts are unreadable")
        when = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise DeploymentValidationError("runtime journal decision_at must be UTC")
        records.append(
            JournalRecord(
                decision_at=when.astimezone(UTC),
                mode=mode,
                capital=capital,
                execution=execution,
            )
        )
    return tuple(sorted(records, key=lambda record: record.decision_at))


def observations_from_journal(
    records: Sequence[JournalRecord],
    *,
    portfolio_id: str,
    definition: DeploymentDefinition,
    fingerprint: str,
    venue: str,
    account_alias: str,
    host_alias: str,
    flows: Sequence[tuple[datetime, Decimal]],
    facts: Mapping[str, str],
    max_age_seconds: int,
    now: datetime,
) -> tuple[CapitalObservation, ...]:
    """Build the capital history this deployment can actually evidence.

    Only journal entries that carry capital facts become observations.  A cycle
    that never reached the venue leaves no mark, so the series stays honest
    about what was observed instead of interpolating.
    """
    authority = authority_from_host(facts)
    last_run = last_run_from_host(facts)
    observations: list[CapitalObservation] = []
    previous_at: datetime | None = None
    for record in records:
        if record.capital is None:
            continue
        capital = record.capital
        as_of_raw = capital.get("as_of")
        if not isinstance(as_of_raw, str):
            raise DeploymentValidationError("journal capital is missing as_of")
        as_of = datetime.fromisoformat(as_of_raw.replace("Z", "+00:00")).astimezone(UTC)
        checks = health_checks_from_host(
            facts,
            expected_fingerprint=fingerprint,
            capital_as_of=as_of,
            execution_trustworthy=record.trustworthy,
            reconciled=record.reconciled,
            now=now,
            max_age_seconds=max_age_seconds,
        )
        observations.append(
            CapitalObservation(
                portfolio_id=portfolio_id,
                family=definition.strategy.family,
                memory_version=definition.strategy.memory_version,
                deployment_fingerprint=fingerprint,
                observed_at=as_of,
                venue=venue,
                account_alias=account_alias,
                host_alias=host_alias,
                equity_usd=_decimal(capital.get("equity_usd"), "equity_usd"),
                cash_usd=_decimal(capital.get("cash_usd"), "cash_usd"),
                gross_exposure_usd=_decimal(capital.get("gross_exposure_usd"), "gross_exposure_usd"),
                net_exposure_usd=_decimal(capital.get("net_exposure_usd"), "net_exposure_usd"),
                external_flow_usd_since_previous=_flow_between(flows, previous_at, as_of),
                realized_pnl_usd=(
                    None
                    if capital.get("daily_realized_pnl_usd") is None
                    else _decimal(capital.get("daily_realized_pnl_usd"), "daily_realized_pnl_usd")
                ),
                unrealized_pnl_usd=_decimal(capital.get("unrealized_pnl_usd"), "unrealized_pnl_usd"),
                fees_usd=(None if capital.get("fees_usd") is None else _decimal(capital.get("fees_usd"), "fees_usd")),
                funding_pnl_usd=(
                    None
                    if capital.get("funding_pnl_usd") is None
                    else _decimal(capital.get("funding_pnl_usd"), "funding_pnl_usd")
                ),
                positions=_positions(capital.get("positions")),
                health_checks=checks,
                authority_facts=authority,
                last_run=last_run,
            )
        )
        previous_at = as_of
    return tuple(observations)


# --------------------------------------------------------------------------- #
# Strategy projection
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DeploymentIdentity:
    """Non-secret deployment, host, and schedule identity for the detail page."""

    family: str
    memory_version: str
    preset: str
    venue: str
    instrument: str
    account_alias: str
    host_alias: str
    host_region: str
    schedule: str
    timezone: str
    host_git_sha: str
    deployment_fingerprint: str

    def to_payload(self) -> dict[str, Any]:
        """Return the JSON-ready identity record."""
        return {
            "family": self.family,
            "memory_version": self.memory_version,
            "preset": self.preset,
            "venue": self.venue,
            "instrument": self.instrument,
            "account_alias": self.account_alias,
            "host_alias": self.host_alias,
            "host_region": self.host_region,
            "schedule": self.schedule,
            "timezone": self.timezone,
            "host_git_sha": self.host_git_sha,
            "deployment_fingerprint": self.deployment_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class StrategyProjection:
    """Everything the projection publishes for one portfolio member."""

    identity: DeploymentIdentity
    observations: tuple[CapitalObservation, ...]
    series: StrategySeries
    runs: tuple[dict[str, Any], ...]
    authority: AuthorityFacts
    health_checks: tuple[HealthCheck, ...]
    last_run: LastRun
    included: bool


def strategy_projection(
    *,
    portfolio_id: str,
    definition: DeploymentDefinition,
    deployment_path: Path,
    fingerprint: str,
    facts: Mapping[str, str],
    state_root: Path,
    account_alias: str,
    host_alias: str,
    host_region: str,
    max_age_seconds: int,
    included: bool,
    now: datetime,
) -> StrategyProjection:
    """Assemble one strategy's projection from host-local truth only."""
    records = decode_journal(journal_entries(state_root, fingerprint))
    flows = read_flows(flows_path(state_root, fingerprint))
    venue = definition.execution.venue
    instrument = definition.execution.instruments[0][1] if definition.execution.instruments else ""
    observations = observations_from_journal(
        records,
        portfolio_id=portfolio_id,
        definition=definition,
        fingerprint=fingerprint,
        venue=venue,
        account_alias=account_alias,
        host_alias=host_alias,
        flows=flows,
        facts=facts,
        max_age_seconds=max_age_seconds,
        now=now,
    )
    latest = records[-1] if records else None
    checks = health_checks_from_host(
        facts,
        expected_fingerprint=fingerprint,
        capital_as_of=observations[-1].observed_at if observations else None,
        execution_trustworthy=latest.trustworthy if latest else None,
        reconciled=latest.reconciled if latest else None,
        now=now,
        max_age_seconds=max_age_seconds,
    )
    identity = DeploymentIdentity(
        family=definition.strategy.family,
        memory_version=definition.strategy.memory_version,
        preset=definition.strategy.preset,
        venue=venue,
        instrument=instrument,
        account_alias=account_alias,
        host_alias=host_alias,
        host_region=host_region,
        schedule=definition.runtime.schedule,
        timezone=definition.runtime.timezone,
        host_git_sha=facts.get("HOST_GIT_SHA", ""),
        deployment_fingerprint=fingerprint,
    )
    runs = tuple(
        {
            "at": record.decision_at.isoformat(),
            "mode": record.mode,
            "trustworthy": record.trustworthy,
            "reconciled": record.reconciled,
            "target_contracts": record.execution.get("target_contracts"),
            "final_contracts": record.execution.get("final_contracts"),
            "commission_usd": record.execution.get("commission_usd"),
            "note": record.execution.get("note"),
        }
        for record in records
    )
    return StrategyProjection(
        identity=identity,
        observations=observations,
        series=strategy_series(
            definition.strategy.family,
            observations,
            max_age_seconds=max_age_seconds,
            now=now,
        ),
        runs=runs,
        authority=authority_from_host(facts),
        health_checks=checks,
        last_run=last_run_from_host(facts),
        included=included,
    )


# --------------------------------------------------------------------------- #
# Payload shaping
# --------------------------------------------------------------------------- #


def _number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _series_payload(points: Sequence[SeriesPoint]) -> list[dict[str, Any]]:
    return [
        {
            "day": point.day.isoformat(),
            "observed_at": point.observed_at.isoformat(),
            "equity_usd": _number(point.equity_usd),
            "cum_pnl_usd": _number(point.cum_pnl_usd),
            "cum_return": _number(point.cum_return),
            "period_pnl_usd": _number(point.period_pnl_usd),
            "complete": True,
        }
        for point in points
    ]


def _aggregate_series_payload(points: Sequence[AggregatePoint]) -> list[dict[str, Any]]:
    return [
        {
            "day": point.day.isoformat(),
            "observed_at": None,
            "equity_usd": _number(point.equity_usd),
            "cum_pnl_usd": _number(point.cum_pnl_usd),
            "cum_return": _number(point.cum_return),
            "period_pnl_usd": _number(point.period_pnl_usd),
            "complete": point.complete,
        }
        for point in points
    ]


def _metrics_payload(metrics: PerformanceMetrics) -> dict[str, Any]:
    return {
        "total_pnl_usd": _number(metrics.total_pnl_usd),
        "total_return": _number(metrics.total_return),
        "max_drawdown": _number(metrics.max_drawdown),
        "annualized_volatility": _number(metrics.annualized_volatility),
        "sharpe": _number(metrics.sharpe),
        "positive_day_rate": _number(metrics.positive_day_rate),
        "observation_count": metrics.observation_count,
    }


def snapshot_payload(
    projection: StrategyProjection,
    *,
    portfolio_id: str,
    weight: Decimal | None,
    generated_at: datetime,
) -> dict[str, Any]:
    """Build one strategy's atomically replaced snapshot document."""
    latest = projection.observations[-1] if projection.observations else None
    series = projection.series
    last_point = series.points[-1] if series.points else None
    payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "portfolio_id": portfolio_id,
        "generated_at": generated_at.isoformat(),
        "family": projection.identity.family,
        "included": projection.included,
        "state": lifecycle_state(projection.authority),
        "health": overall_health(projection.health_checks, projection.authority),
        "stale": series.stale,
        "max_age_seconds": series.max_age_seconds,
        "last_observation_at": None if latest is None else latest.observed_at.isoformat(),
        "today_pnl_usd": None if last_point is None else _number(last_point.period_pnl_usd),
        "inception_pnl_usd": None if last_point is None else _number(last_point.cum_pnl_usd),
        "deployment": projection.identity.to_payload(),
        "authority_facts": projection.authority.to_payload(),
        "health_checks": [check.to_payload() for check in projection.health_checks],
        "last_run": projection.last_run.to_payload(),
        "capital": (
            None
            if latest is None
            else {
                "as_of": latest.observed_at.isoformat(),
                "equity_usd": _number(latest.equity_usd),
                "cash_usd": _number(latest.cash_usd),
                "gross_exposure_usd": _number(latest.gross_exposure_usd),
                "net_exposure_usd": _number(latest.net_exposure_usd),
                "realized_pnl_usd": _number(latest.realized_pnl_usd),
                "unrealized_pnl_usd": _number(latest.unrealized_pnl_usd),
                "fees_usd": _number(latest.fees_usd),
                "funding_pnl_usd": _number(latest.funding_pnl_usd),
                "capital_weight": _number(weight),
                "positions": [position.to_payload() for position in latest.positions],
            }
        ),
        "metrics": _metrics_payload(performance_metrics(series.points)),
        "series": _series_payload(series.points),
    }
    assert_redacted(payload)
    return payload


def overview_payload(
    *,
    manifest: PortfolioManifest,
    projections: Mapping[str, StrategyProjection],
    generated_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    """Build the atomically replaced portfolio overview document."""
    aggregate = aggregate_series(
        manifest,
        {family: projection.series for family, projection in projections.items()},
        now=now,
    )
    metrics = performance_metrics(aggregate.points)
    members = []
    for member in manifest.members:
        projection = projections.get(member.family)
        if projection is None:
            members.append(
                {
                    "family": member.family,
                    "included": member.included,
                    "state": None,
                    "health": "unknown",
                    "stale": True,
                    "capital_weight": None,
                    "equity_usd": None,
                    "inception_pnl_usd": None,
                    "period_pnl_usd": None,
                    "last_observation_at": None,
                }
            )
            continue
        series = projection.series
        latest_point = series.points[-1] if series.points else None
        members.append(
            {
                "family": member.family,
                "included": member.included,
                "state": lifecycle_state(projection.authority),
                "health": overall_health(projection.health_checks, projection.authority),
                "stale": series.stale,
                "capital_weight": _number(aggregate.weights.get(member.family)),
                "equity_usd": _number(series.equity_usd),
                "inception_pnl_usd": None if latest_point is None else _number(latest_point.cum_pnl_usd),
                "period_pnl_usd": None if latest_point is None else _number(latest_point.period_pnl_usd),
                "last_observation_at": (None if latest_point is None else latest_point.observed_at.isoformat()),
            }
        )
    complete_points = [point for point in aggregate.points if point.complete]
    final = complete_points[-1] if complete_points else None
    payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "portfolio_id": manifest.portfolio_id,
        "generated_at": generated_at.isoformat(),
        "completeness": aggregate.completeness,
        "equity_usd": _number(aggregate.equity_usd),
        "today_pnl_usd": None if final is None else _number(final.period_pnl_usd),
        "inception_pnl_usd": None if final is None else _number(final.cum_pnl_usd),
        "missing_families": list(aggregate.missing_families),
        "stale_families": list(aggregate.stale_families),
        "included_families": list(aggregate.included_families),
        "metrics": _metrics_payload(metrics),
        "members": members,
        "series": _aggregate_series_payload(aggregate.points),
        "strategy_series": {
            family: _series_payload(projection.series.points) for family, projection in projections.items()
        },
    }
    assert_redacted(payload)
    return payload


# --------------------------------------------------------------------------- #
# Durable writes
# --------------------------------------------------------------------------- #


def _read_text(path: Path, *, missing_ok: bool) -> str | None:
    """Read one regular file without following a final-component symlink."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        handle = os.open(path, flags)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise DeploymentValidationError(f"file does not exist: {path}") from None
    except OSError as exc:
        raise DeploymentValidationError(f"file is not readable: {path}") from exc
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            raise DeploymentValidationError(f"file is not a regular file: {path}")
        if info.st_size > _MAX_READ_BYTES:
            raise DeploymentValidationError(f"file is too large to read: {path}")
        return os.read(handle, _MAX_READ_BYTES).decode("utf-8")
    finally:
        os.close(handle)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Replace one document atomically after fsyncing its contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path


def _append_new_lines(path: Path, records: Sequence[Mapping[str, Any]], *, key: str) -> int:
    """Append only records newer than the file's last entry, keeping it append-only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_text(path, missing_ok=True)
    last_key: str | None = None
    if existing:
        for line in reversed(existing.splitlines()):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DeploymentValidationError(f"projection history is unreadable: {path}") from exc
            if isinstance(payload, Mapping) and isinstance(payload.get(key), str):
                last_key = payload[key]
            break
    pending = [record for record in records if last_key is None or str(record[key]) > last_key]
    if not pending:
        return 0
    with path.open("a", encoding="utf-8") as stream:
        for record in pending:
            assert_redacted(record)
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return len(pending)


def publish_projection(
    *,
    db_root: Path,
    manifest: PortfolioManifest,
    projections: Mapping[str, StrategyProjection],
    now: datetime,
) -> dict[str, Any]:
    """Write the whole projection: snapshots replaced, history appended.

    Returns a small report of what changed so an operator can see whether a
    cycle actually added observations.
    """
    root = db_root / PROJECTION_DIR
    aggregate = aggregate_series(
        manifest,
        {family: projection.series for family, projection in projections.items()},
        now=now,
    )
    report: dict[str, Any] = {"portfolio_id": manifest.portfolio_id, "strategies": {}}
    for family, projection in projections.items():
        manifest.member(family)
        directory = root / STRATEGIES_DIR / family
        appended = _append_new_lines(
            directory / OBSERVATIONS_FILE,
            [observation.to_payload() for observation in projection.observations],
            key="observed_at",
        )
        runs_appended = _append_new_lines(directory / RUNS_FILE, projection.runs, key="at")
        _atomic_write_json(
            directory / SNAPSHOT_FILE,
            snapshot_payload(
                projection,
                portfolio_id=manifest.portfolio_id,
                weight=aggregate.weights.get(family),
                generated_at=now,
            ),
        )
        report["strategies"][family] = {
            "observations_appended": appended,
            "runs_appended": runs_appended,
        }
    _atomic_write_json(
        root / OVERVIEW_FILE,
        overview_payload(manifest=manifest, projections=projections, generated_at=now, now=now),
    )
    report["completeness"] = aggregate.completeness
    return report


__all__ = [
    "OBSERVATIONS_FILE",
    "OVERVIEW_FILE",
    "PROJECTION_DIR",
    "PROJECTION_SCHEMA_VERSION",
    "RUNS_FILE",
    "SNAPSHOT_FILE",
    "STRATEGIES_DIR",
    "DeploymentIdentity",
    "JournalRecord",
    "StrategyProjection",
    "authority_from_host",
    "decode_journal",
    "flows_path",
    "health_checks_from_host",
    "host_facts",
    "last_run_from_host",
    "observations_from_journal",
    "overview_payload",
    "publish_projection",
    "read_flows",
    "snapshot_payload",
    "strategy_projection",
]
