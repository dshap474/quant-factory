"""Shared builders for redacted capital observations used across tests.

USAGE: from observation_builders import authority, checks, observation
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from production.observation import (
    HEALTH_CHECK_NAMES,
    AuthorityFacts,
    CapitalObservation,
    HealthCheck,
    LastRun,
)

FINGERPRINT = "a" * 64


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def checks(state: str = "passing") -> tuple[HealthCheck, ...]:
    return tuple(HealthCheck(name=name, state=state, detail="observed") for name in HEALTH_CHECK_NAMES)


def authority(**overrides: object) -> AuthorityFacts:
    facts: dict[str, Any] = {
        "activation_state": "missing",
        "activation_expires_at": None,
        "armed": False,
        "venue_gate": "closed",
        "capital_gate": "closed",
        "deactivated": False,
        "can_trade": False,
        "scheduled": False,
        "autonomous_live": False,
    }
    facts.update(overrides)
    return AuthorityFacts(**facts)


def observation(**overrides: object) -> CapitalObservation:
    fields: dict[str, Any] = {
        "portfolio_id": "qf-production",
        "family": "example-family",
        "memory_version": "v001",
        "deployment_fingerprint": FINGERPRINT,
        "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
        "venue": "example-venue",
        "account_alias": "example-account",
        "host_alias": "prod-a",
        "equity_usd": Decimal("10000"),
        "cash_usd": Decimal("9500"),
        "gross_exposure_usd": Decimal("1000"),
        "net_exposure_usd": Decimal("1000"),
        "external_flow_usd_since_previous": Decimal("0"),
        "realized_pnl_usd": None,
        "unrealized_pnl_usd": Decimal("500"),
        "fees_usd": None,
        "funding_pnl_usd": None,
        "positions": (),
        "health_checks": checks(),
        "authority_facts": authority(),
        "last_run": LastRun(result="never", at=None, mode=None, journal_at=None),
    }
    fields.update(overrides)
    return CapitalObservation(**fields)
