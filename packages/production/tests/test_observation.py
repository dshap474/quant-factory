"""Tests for the normalized capital-observation contract and redaction guard.

USAGE: uv run --package quant-factory-production pytest packages/production/tests/test_observation.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from observation_builders import FINGERPRINT, authority, checks, observation
from production.contracts import DeploymentValidationError
from production.observation import (
    HEALTH_CHECK_NAMES,
    CapitalObservation,
    HealthCheck,
    LastRun,
    PortfolioManifest,
    PositionObservation,
    RedactionError,
    assert_redacted,
    lifecycle_state,
    overall_health,
)

# --------------------------------------------------------------------------- #
# Contract validation
# --------------------------------------------------------------------------- #


def test_payload_round_trips() -> None:
    original = observation(
        positions=(
            PositionObservation(
                instrument="EXAMPLE-PERP",
                side="LONG",
                quantity=Decimal("0.01"),
                contracts=1,
                current_price=Decimal("100000"),
                entry_price=Decimal("95000"),
                market_value_usd=Decimal("1000"),
                unrealized_pnl_usd=Decimal("50"),
                daily_realized_pnl_usd=Decimal("0"),
            ),
        )
    )
    payload = original.to_payload()
    rebuilt = CapitalObservation.from_payload(payload)
    assert rebuilt.to_payload() == payload
    assert rebuilt.positions[0].instrument == "EXAMPLE-PERP"


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(DeploymentValidationError):
        observation(observed_at=datetime(2026, 8, 20))


def test_missing_health_check_is_rejected() -> None:
    with pytest.raises(DeploymentValidationError, match="missing"):
        observation(health_checks=checks()[:-1])


def test_duplicate_health_check_is_rejected() -> None:
    duplicated = (*checks(), HealthCheck(name="scheduler", state="failing", detail="dup"))
    with pytest.raises(DeploymentValidationError, match="duplicate"):
        observation(health_checks=duplicated)


def test_autonomous_live_requires_can_trade_and_schedule() -> None:
    with pytest.raises(DeploymentValidationError, match="autonomous_live"):
        authority(autonomous_live=True)


def test_last_run_never_cannot_carry_a_timestamp() -> None:
    with pytest.raises(DeploymentValidationError):
        LastRun(result="never", at=datetime(2026, 8, 20, tzinfo=UTC), mode=None, journal_at=None)


def test_account_alias_must_be_an_alias_not_an_identifier() -> None:
    with pytest.raises(DeploymentValidationError):
        observation(account_alias="8f14e45f-ceea-467a-9f31-9a1d0a3f5c2b")


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "value"},
        {"credential_name_hash": "abc"},
        {"account_id": 1},
        {"activation_receipt": {}},
        {"portfolio_uuid": "x"},
        {"nested": [{"secret": "x"}]},
    ],
)
def test_forbidden_keys_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(RedactionError):
        assert_redacted(payload)


def test_raw_identifier_value_fails_closed() -> None:
    with pytest.raises(RedactionError, match="raw identifier"):
        assert_redacted({"order_reference": "8f14e45f-ceea-467a-9f31-9a1d0a3f5c2b"})


def test_key_material_fails_closed() -> None:
    with pytest.raises(RedactionError, match="key material"):
        assert_redacted({"note": "-----BEGIN EC PRIVATE KEY-----\nabc\n"})


def test_unexpected_hex_digest_fails_closed() -> None:
    with pytest.raises(RedactionError, match="hex digest"):
        assert_redacted({"note": FINGERPRINT})


def test_fingerprint_is_allowlisted() -> None:
    assert_redacted({"deployment_fingerprint": FINGERPRINT})


def test_published_observation_is_redacted() -> None:
    assert_redacted(observation().to_payload())


# --------------------------------------------------------------------------- #
# Lifecycle and health
# --------------------------------------------------------------------------- #


def test_registered_deployment_is_not_live() -> None:
    facts = authority()
    assert lifecycle_state(facts) == "registered"
    assert facts.autonomous_live is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"deactivated": True}, "deactivated"),
        ({"activation_state": "enabled"}, "activated"),
        ({"activation_state": "expired"}, "activation-expired"),
        ({"activation_state": "enabled", "can_trade": True}, "authorized"),
        (
            {
                "activation_state": "enabled",
                "can_trade": True,
                "scheduled": True,
                "autonomous_live": True,
            },
            "autonomous-live",
        ),
    ],
)
def test_lifecycle_states(overrides: dict[str, object], expected: str) -> None:
    assert lifecycle_state(authority(**overrides)) == expected


def test_deactivation_reports_paused_not_failure() -> None:
    assert overall_health(checks("failing"), authority(deactivated=True)) == "paused"


def test_unknown_check_does_not_pass() -> None:
    mixed = (
        HealthCheck(name="deployment_identity", state="passing", detail="ok"),
        HealthCheck(name="scheduler", state="unknown", detail="units not installed"),
        *[HealthCheck(name=name, state="passing", detail="ok") for name in HEALTH_CHECK_NAMES[2:]],
    )
    assert overall_health(mixed, authority()) == "unknown"


def test_failing_check_reports_attention() -> None:
    assert overall_health(checks("failing"), authority()) == "attention"


def test_all_passing_reports_healthy() -> None:
    assert overall_health(checks(), authority()) == "healthy"


# --------------------------------------------------------------------------- #
# Portfolio manifest
# --------------------------------------------------------------------------- #


def test_unknown_manifest_field_is_rejected() -> None:
    with pytest.raises(DeploymentValidationError, match="unknown fields"):
        PortfolioManifest.from_mapping(
            {
                "schema_version": 1,
                "portfolio_id": "qf-production",
                "members": [{"family": "example-family", "included": True, "account_snapshot_max_age_seconds": 1}],
                "authorized": True,
            }
        )


def test_unknown_family_is_not_a_member() -> None:
    manifest = PortfolioManifest.from_mapping(
        {
            "schema_version": 1,
            "portfolio_id": "qf-production",
            "members": [{"family": "example-family", "included": True, "account_snapshot_max_age_seconds": 1}],
        }
    )
    with pytest.raises(DeploymentValidationError, match="not a declared portfolio member"):
        manifest.member("example-strategy")
