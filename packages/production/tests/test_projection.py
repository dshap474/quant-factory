"""Tests for the read-only production telemetry projection.

USAGE: uv run --package quant-factory-production pytest packages/production/tests/test_projection.py -q
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from observation_builders import FINGERPRINT
from production.aggregation import strategy_series
from production.contracts import DeploymentDefinition, DeploymentValidationError
from production.observation import PortfolioManifest, RedactionError
from production.projection import (
    OBSERVATIONS_FILE,
    OVERVIEW_FILE,
    RUNS_FILE,
    SNAPSHOT_FILE,
    STRATEGIES_DIR,
    DeploymentIdentity,
    StrategyProjection,
    authority_from_host,
    decode_journal,
    health_checks_from_host,
    host_facts,
    last_run_from_host,
    observations_from_journal,
    overview_payload,
    publish_projection,
    read_flows,
    snapshot_payload,
    strategy_projection,
)

NOW = datetime(2026, 8, 20, 1, tzinfo=UTC)
GIT_SHA = "0" * 40


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def definition() -> DeploymentDefinition:
    return DeploymentDefinition.from_mapping(
        {
            "schema_version": 2,
            "strategy": {"family": "example-family", "memory_version": "v001", "preset": "v001"},
            "runtime": {
                "schedule": "*-*-* 00:00:00",
                "timezone": "UTC",
                "max_decision_age_seconds": 60,
            },
            "execution": {"venue": "example-venue", "instruments": {"ASSET": "EXAMPLE-PERP"}},
        }
    )


def facts(**overrides: str) -> dict[str, str]:
    """Today's honest example-family host facts: registered, valid, run by hand."""
    base = {
        "REGISTERED": "yes",
        "HOST_GIT_SHA": GIT_SHA,
        "DEPLOYMENT_FINGERPRINT": FINGERPRINT,
        "ACTIVATION_RECEIPT": "missing",
        "ACTIVATION_EXPIRES_AT": "n/a",
        "ACTIVATION_CAPPED": "no",
        "ARMED": "no",
        "VENUE_GATE": "closed",
        "CAPITAL_APPROVAL": "closed",
        "DEACTIVATED": "no",
        "CAN_TRADE": "no",
        "SCHEDULED": "no",
        "AUTONOMOUS_LIVE": "no",
        "LAST_RUN": "never",
        "RUNTIME_JOURNAL": "never",
    }
    base.update(overrides)
    return base


def journal_entry(offset_days: int, equity: str, *, mode: str = "live") -> dict[str, Any]:
    at = (NOW - timedelta(days=offset_days)).isoformat()
    return {
        "deployment_fingerprint": FINGERPRINT,
        "family": "example-family",
        "memory_version": "v001",
        "decision_at": at,
        "observed_through": at,
        "mode": mode,
        "execution": {
            "product_id": "EXAMPLE-PERP",
            "target_contracts": 1,
            "final_contracts": 1,
            "dry_run": mode == "dry-run",
            "previewed": True,
            "close_status": None,
            "open_status": "FILLED",
            "commission_usd": "0.5",
            "trustworthy": True,
            "note": None,
        },
        "capital": {
            "as_of": at,
            "equity_usd": equity,
            "cash_usd": equity,
            "available_margin_usd": equity,
            "initial_margin_usd": "100",
            "liquidation_buffer_usd": "500",
            "gross_exposure_usd": "1000",
            "net_exposure_usd": "1000",
            "unrealized_pnl_usd": "0",
            "daily_realized_pnl_usd": "0",
            "funding_rate": "0.0001",
            "positions": [
                {
                    "instrument": "EXAMPLE-PERP",
                    "side": "LONG",
                    "contracts": 1,
                    "quantity": "0.01",
                    "current_price": "100000",
                    "entry_price": "95000",
                    "market_value_usd": "1000",
                    "unrealized_pnl_usd": "50",
                    "daily_realized_pnl_usd": "0",
                }
            ],
        },
    }


def manifest() -> PortfolioManifest:
    return PortfolioManifest.from_mapping(
        {
            "schema_version": 1,
            "portfolio_id": "qf-production",
            "members": [
                {
                    "family": "example-family",
                    "included": True,
                    "account_snapshot_max_age_seconds": 172_800,
                }
            ],
        }
    )


def write_journal(state_root: Path, entries: list[dict[str, Any]]) -> None:
    path = state_root / "journals" / FINGERPRINT / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")


def write_flows(state_root: Path, entries: list[tuple[int, str]]) -> None:
    path = state_root / "flows" / FINGERPRINT / "flows.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps({"at": (NOW - timedelta(days=offset)).isoformat(), "amount_usd": amount}) + "\n"
            for offset, amount in entries
        ),
        encoding="utf-8",
    )


def build_projection(state_root: Path, *, included: bool = True) -> StrategyProjection:
    return strategy_projection(
        portfolio_id="qf-production",
        definition=definition(),
        deployment_path=Path("packages/production/extensions/deployments/example-family/deployment.yaml"),
        fingerprint=FINGERPRINT,
        facts=facts(),
        state_root=state_root,
        account_alias="example-account",
        host_alias="prod-a",
        host_region="region-a",
        max_age_seconds=172_800,
        included=included,
        now=NOW,
    )


# --------------------------------------------------------------------------- #
# Host fact decoding
# --------------------------------------------------------------------------- #


def test_host_facts_reject_duplicates() -> None:
    with pytest.raises(DeploymentValidationError, match="duplicate host fact"):
        host_facts((("ARMED", "no"), ("ARMED", "yes")))


def test_registered_but_unscheduled_is_not_autonomous_live() -> None:
    authority = authority_from_host(facts())
    assert authority.autonomous_live is False
    assert authority.scheduled is False
    assert authority.can_trade is False
    assert authority.activation_state == "missing"


def test_scheduler_is_unknown_because_cycles_run_by_hand() -> None:
    checks = {
        check.name: check
        for check in health_checks_from_host(
            facts(),
            expected_fingerprint=FINGERPRINT,
            capital_as_of=None,
            execution_trustworthy=None,
            reconciled=None,
            now=NOW,
            max_age_seconds=172_800,
        )
    }
    assert checks["scheduler"].state == "unknown"
    assert "by hand" in checks["scheduler"].detail
    assert checks["pipeline"].state == "unknown"
    assert checks["account_snapshot"].state == "unknown"
    assert checks["deployment_identity"].state == "passing"


def test_fingerprint_mismatch_fails_the_identity_check() -> None:
    checks = {
        check.name: check
        for check in health_checks_from_host(
            facts(DEPLOYMENT_FINGERPRINT="b" * 64),
            expected_fingerprint=FINGERPRINT,
            capital_as_of=None,
            execution_trustworthy=None,
            reconciled=None,
            now=NOW,
            max_age_seconds=172_800,
        )
    }
    assert checks["deployment_identity"].state == "failing"


def test_last_run_never_has_no_timestamp() -> None:
    last_run = last_run_from_host(facts())
    assert last_run.result == "never"
    assert last_run.at is None
    assert last_run.journal_at is None


def test_contradictory_last_run_fails_closed() -> None:
    with pytest.raises(DeploymentValidationError):
        last_run_from_host(facts(LAST_RUN="success"))


# --------------------------------------------------------------------------- #
# Cash flows
# --------------------------------------------------------------------------- #


def test_missing_flow_ledger_is_empty(tmp_path: Path) -> None:
    assert read_flows(tmp_path / "flows.jsonl") == ()


def test_unreadable_flow_ledger_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "flows.jsonl"
    path.write_text('{"at": "2026-08-20T00:00:00+00:00"}\n', encoding="utf-8")
    with pytest.raises(DeploymentValidationError):
        read_flows(path)


def test_naive_flow_timestamp_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "flows.jsonl"
    path.write_text('{"at": "2026-08-20T00:00:00", "amount_usd": "1"}\n', encoding="utf-8")
    with pytest.raises(DeploymentValidationError):
        read_flows(path)


def test_deposit_is_removed_from_observed_pnl(tmp_path: Path) -> None:
    write_journal(
        tmp_path,
        [journal_entry(2, "10000"), journal_entry(1, "15100"), journal_entry(0, "15200")],
    )
    write_flows(tmp_path, [(1, "5000")])
    projection = build_projection(tmp_path)
    assert [point.period_pnl_usd for point in projection.series.points] == [
        None,
        Decimal("100"),
        Decimal("100"),
    ]
    assert projection.series.points[-1].cum_pnl_usd == Decimal("200")


def test_withdrawal_is_removed_from_observed_pnl(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(1, "10000"), journal_entry(0, "8100")])
    write_flows(tmp_path, [(0, "-2000")])
    projection = build_projection(tmp_path)
    assert projection.series.points[-1].cum_pnl_usd == Decimal("100")


def test_flow_before_inception_funds_the_baseline(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    write_flows(tmp_path, [(5, "10000")])
    projection = build_projection(tmp_path)
    assert projection.series.points[0].external_flow_usd == Decimal("0")
    assert projection.series.points[-1].cum_pnl_usd == Decimal("100")


# --------------------------------------------------------------------------- #
# Journal decoding
# --------------------------------------------------------------------------- #


def test_journal_without_capital_yields_no_observations(tmp_path: Path) -> None:
    entry = journal_entry(0, "10000")
    del entry["capital"]
    write_journal(tmp_path, [entry])
    projection = build_projection(tmp_path)
    assert projection.observations == ()
    assert projection.series.has_capital is False
    assert projection.runs != ()
    # The cycle ran, so execution is judged even without capital facts.
    checks = {check.name: check.state for check in projection.health_checks}
    assert checks["account_snapshot"] == "unknown"
    assert checks["execution"] == "passing"


def test_contradictory_journal_mode_fails_closed() -> None:
    with pytest.raises(DeploymentValidationError):
        decode_journal([{"decision_at": NOW.isoformat(), "mode": "maybe", "execution": {}}])


def test_journal_is_ordered_oldest_first() -> None:
    records = decode_journal([journal_entry(0, "2"), journal_entry(3, "1")])
    assert records[0].decision_at < records[1].decision_at


def test_untrustworthy_execution_fails_the_check(tmp_path: Path) -> None:
    entry = journal_entry(0, "10000")
    entry["execution"]["trustworthy"] = False
    write_journal(tmp_path, [entry])
    projection = build_projection(tmp_path)
    checks = {check.name: check.state for check in projection.health_checks}
    assert checks["execution"] == "failing"


def test_position_mismatch_fails_reconciliation(tmp_path: Path) -> None:
    entry = journal_entry(0, "10000")
    entry["execution"]["final_contracts"] = 0
    write_journal(tmp_path, [entry])
    projection = build_projection(tmp_path)
    checks = {check.name: check.state for check in projection.health_checks}
    assert checks["reconciliation"] == "failing"


def test_observations_are_redacted(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(0, "10000")])
    projection = build_projection(tmp_path)
    for observation in projection.observations:
        observation.to_payload()


def test_capital_carrying_a_provider_identifier_fails_closed() -> None:
    entry = journal_entry(0, "10000")
    entry["capital"]["positions"][0]["instrument"] = "EXAMPLE-PERP"
    records = decode_journal([entry])
    observations = observations_from_journal(
        records,
        portfolio_id="qf-production",
        definition=definition(),
        fingerprint=FINGERPRINT,
        venue="example-venue",
        account_alias="example-account",
        host_alias="prod-a",
        flows=(),
        facts=facts(),
        max_age_seconds=172_800,
        now=NOW,
    )
    payload = observations[0].to_payload()
    assert "credential" not in json.dumps(payload)
    assert "order_id" not in json.dumps(payload)


# --------------------------------------------------------------------------- #
# Published documents
# --------------------------------------------------------------------------- #


def test_snapshot_reports_registered_and_unknown_health(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(0, "10000")])
    projection = build_projection(tmp_path)
    payload = snapshot_payload(projection, portfolio_id="qf-production", weight=Decimal("1"), generated_at=NOW)
    assert payload["state"] == "registered"
    assert payload["health"] == "unknown"
    assert payload["capital"]["equity_usd"] == 10000.0
    assert payload["capital"]["capital_weight"] == 1.0
    # One mark supports an equity level but no return metrics.
    assert payload["metrics"]["sharpe"] is None
    assert payload["metrics"]["total_return"] is None
    assert payload["metrics"]["observation_count"] == 0


def test_snapshot_without_capital_omits_it_rather_than_zeroing(tmp_path: Path) -> None:
    projection = build_projection(tmp_path)
    payload = snapshot_payload(projection, portfolio_id="qf-production", weight=None, generated_at=NOW)
    assert payload["capital"] is None
    assert payload["series"] == []
    assert payload["stale"] is True
    assert payload["metrics"]["total_pnl_usd"] is None


def test_overview_is_empty_when_no_member_has_capital(tmp_path: Path) -> None:
    payload = overview_payload(
        manifest=manifest(),
        projections={"example-family": build_projection(tmp_path)},
        generated_at=NOW,
        now=NOW,
    )
    assert payload["completeness"] == "empty"
    assert payload["equity_usd"] is None
    assert payload["missing_families"] == ["example-family"]
    assert payload["members"][0]["state"] == "registered"
    assert payload["members"][0]["capital_weight"] is None


def test_overview_weights_sum_to_one_when_complete(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    payload = overview_payload(
        manifest=manifest(),
        projections={"example-family": build_projection(tmp_path)},
        generated_at=NOW,
        now=NOW,
    )
    assert payload["completeness"] == "complete"
    assert payload["equity_usd"] == 10100.0
    assert payload["members"][0]["capital_weight"] == 1.0


def test_overview_is_stale_when_the_only_mark_is_old(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(30, "10000")])
    payload = overview_payload(
        manifest=manifest(),
        projections={"example-family": build_projection(tmp_path)},
        generated_at=NOW,
        now=NOW,
    )
    assert payload["completeness"] == "stale"
    assert payload["equity_usd"] is None
    assert payload["stale_families"] == ["example-family"]


def test_overview_incomplete_when_one_included_member_is_missing(tmp_path: Path) -> None:
    write_journal(tmp_path, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    two = PortfolioManifest.from_mapping(
        {
            "schema_version": 1,
            "portfolio_id": "qf-production",
            "members": [
                {"family": "example-family", "included": True, "account_snapshot_max_age_seconds": 172_800},
                {"family": "example-strategy", "included": True, "account_snapshot_max_age_seconds": 172_800},
            ],
        }
    )
    payload = overview_payload(
        manifest=two,
        projections={"example-family": build_projection(tmp_path)},
        generated_at=NOW,
        now=NOW,
    )
    assert payload["completeness"] == "incomplete"
    assert payload["missing_families"] == ["example-strategy"]
    # The present member's equity must not be published as the portfolio total.
    assert payload["equity_usd"] is None
    assert payload["members"][0]["capital_weight"] is None


# --------------------------------------------------------------------------- #
# Publication
# --------------------------------------------------------------------------- #


def test_publish_writes_the_documented_layout(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    db_root = tmp_path / "db"
    write_journal(state_root, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    report = publish_projection(
        db_root=db_root,
        manifest=manifest(),
        projections={"example-family": build_projection(state_root)},
        now=NOW,
    )
    strategy_dir = db_root / "production" / STRATEGIES_DIR / "example-family"
    assert (db_root / "production" / OVERVIEW_FILE).is_file()
    assert (strategy_dir / SNAPSHOT_FILE).is_file()
    assert (strategy_dir / OBSERVATIONS_FILE).is_file()
    assert (strategy_dir / RUNS_FILE).is_file()
    assert report["strategies"]["example-family"]["observations_appended"] == 2
    assert report["completeness"] == "complete"


def test_history_is_append_only_and_idempotent(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    db_root = tmp_path / "db"
    write_journal(state_root, [journal_entry(1, "10000")])
    publish_projection(
        db_root=db_root,
        manifest=manifest(),
        projections={"example-family": build_projection(state_root)},
        now=NOW,
    )
    observations = db_root / "production" / STRATEGIES_DIR / "example-family" / OBSERVATIONS_FILE
    first = observations.read_text(encoding="utf-8")

    # Republishing the same history appends nothing.
    report = publish_projection(
        db_root=db_root,
        manifest=manifest(),
        projections={"example-family": build_projection(state_root)},
        now=NOW,
    )
    assert report["strategies"]["example-family"]["observations_appended"] == 0
    assert observations.read_text(encoding="utf-8") == first

    # A new cycle appends without rewriting prior lines.
    write_journal(state_root, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    report = publish_projection(
        db_root=db_root,
        manifest=manifest(),
        projections={"example-family": build_projection(state_root)},
        now=NOW,
    )
    assert report["strategies"]["example-family"]["observations_appended"] == 1
    assert observations.read_text(encoding="utf-8").startswith(first)


def test_publishing_an_undeclared_family_fails_closed(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    write_journal(state_root, [journal_entry(0, "10000")])
    projection = build_projection(state_root)
    other = StrategyProjection(
        identity=DeploymentIdentity(
            family="example-strategy",
            memory_version="v001",
            preset="v001",
            venue="example-venue",
            instrument="EXAMPLE-PERP",
            account_alias="example-account",
            host_alias="prod-a",
            host_region="region-a",
            schedule="*-*-* 00:00:00",
            timezone="UTC",
            host_git_sha=GIT_SHA,
            deployment_fingerprint=FINGERPRINT,
        ),
        observations=(),
        series=strategy_series("example-strategy", (), max_age_seconds=172_800, now=NOW),
        runs=(),
        authority=projection.authority,
        health_checks=projection.health_checks,
        last_run=projection.last_run,
        included=True,
    )
    with pytest.raises(DeploymentValidationError, match="not a declared portfolio member"):
        publish_projection(
            db_root=tmp_path / "db",
            manifest=manifest(),
            projections={"example-strategy": other},
            now=NOW,
        )


def test_published_documents_contain_no_forbidden_facts(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    db_root = tmp_path / "db"
    write_journal(state_root, [journal_entry(1, "10000"), journal_entry(0, "10100")])
    publish_projection(
        db_root=db_root,
        manifest=manifest(),
        projections={"example-family": build_projection(state_root)},
        now=NOW,
    )
    for path in (db_root / "production").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in ("credential", "secret", "api_key", "private", "portfolio_uuid", "order_id"):
            assert forbidden not in text.lower(), f"{path} leaked {forbidden}"


def test_symlinked_history_fails_closed(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    db_root = tmp_path / "db"
    write_journal(state_root, [journal_entry(0, "10000")])
    target = tmp_path / "elsewhere.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    history = db_root / "production" / STRATEGIES_DIR / "example-family" / OBSERVATIONS_FILE
    history.parent.mkdir(parents=True, exist_ok=True)
    history.symlink_to(target)
    with pytest.raises(DeploymentValidationError):
        publish_projection(
            db_root=db_root,
            manifest=manifest(),
            projections={"example-family": build_projection(state_root)},
            now=NOW,
        )


def test_forbidden_run_record_fails_closed() -> None:
    with pytest.raises(RedactionError):
        from production.observation import assert_redacted

        assert_redacted({"at": NOW.isoformat(), "provider_order_id": "abc", "api_key": "x"})
