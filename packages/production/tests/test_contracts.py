"""Test provider-neutral deployment and schema-v1 activation contracts.

USAGE: ``uv run --package quant-factory-production pytest packages/production/tests/test_contracts.py -q``.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import cast

import pytest
from production.contracts import ActivationReceipt, DeploymentDefinition, DeploymentValidationError
from production.registry import UnsupportedActivationSchemaError, parse_activation_receipt

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def valid_mapping() -> dict[str, object]:
    return {
        "schema_version": 2,
        "strategy": {"family": "example-family", "memory_version": "v001", "preset": "default"},
        "runtime": {"schedule": "*-*-* 00:05:00", "timezone": "UTC", "max_decision_age_seconds": 60},
        "execution": {"venue": "example-venue", "instruments": {"ASSET": "EXAMPLE-PERP"}},
    }


# --------------------------------------------------------------------------- #
# Deployment contracts
# --------------------------------------------------------------------------- #


def test_valid_definition_contains_identity_cadence_and_routing(valid_mapping: dict[str, object]) -> None:
    definition = DeploymentDefinition.from_mapping(valid_mapping)
    assert definition.strategy.memory_version == "v001"
    assert definition.runtime.max_decision_age_seconds == 60
    assert definition.execution.instrument_for("ASSET") == "EXAMPLE-PERP"


@pytest.mark.parametrize("memory_version", ["1", "v1", "V001", "v0001"])
def test_memory_version_must_match_vnnn(valid_mapping: dict[str, object], memory_version: str) -> None:
    raw = deepcopy(valid_mapping)
    cast(dict[str, object], raw["strategy"])["memory_version"] = memory_version
    with pytest.raises(DeploymentValidationError, match="must match vNNN"):
        DeploymentDefinition.from_mapping(raw)


@pytest.mark.parametrize("field", ["stage", "enabled", "dry_run_default"])
def test_tracked_authority_shaped_fields_are_rejected(valid_mapping: dict[str, object], field: str) -> None:
    raw = deepcopy(valid_mapping)
    section = "runtime" if field == "stage" else "execution"
    cast(dict[str, object], raw[section])[field] = True
    with pytest.raises(DeploymentValidationError, match="unknown fields"):
        DeploymentDefinition.from_mapping(raw)


def test_timezone_must_be_utc(valid_mapping: dict[str, object]) -> None:
    raw = deepcopy(valid_mapping)
    cast(dict[str, object], raw["runtime"])["timezone"] = "local"
    with pytest.raises(DeploymentValidationError, match="must be UTC"):
        DeploymentDefinition.from_mapping(raw)


# --------------------------------------------------------------------------- #
# Generic activation contract
# --------------------------------------------------------------------------- #


def test_activation_is_hash_bound_expiring_and_positive() -> None:
    receipt = ActivationReceipt.from_mapping(
        {
            "schema_version": 1,
            "deployment_fingerprint": "a" * 64,
            "mode": "live",
            "account_id": "account-1",
            "max_position_notional_usd": "5",
            "max_order_notional_usd": "5",
            "expires_at": "2026-01-02T00:00:00Z",
            "enabled": True,
        }
    )
    assert (
        parse_activation_receipt(
            {
                "schema_version": 1,
                "deployment_fingerprint": "a" * 64,
                "mode": "live",
                "account_id": "account-1",
                "max_position_notional_usd": "5",
                "max_order_notional_usd": "5",
                "expires_at": "2026-01-02T00:00:00Z",
                "enabled": True,
            }
        )
        == receipt
    )
    receipt.validate_current(fingerprint="a" * 64, now=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(DeploymentValidationError, match="expired"):
        receipt.validate_current(fingerprint="a" * 64, now=datetime(2026, 1, 2, tzinfo=UTC))


def test_uninstalled_activation_schema_has_typed_failure() -> None:
    with pytest.raises(UnsupportedActivationSchemaError, match="unsupported activation"):
        parse_activation_receipt({"schema_version": 99})
