"""Tests for cash-flow-adjusted P&L, capital weights, and aggregation.

USAGE: uv run --package quant-factory-production pytest packages/production/tests/test_aggregation.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from observation_builders import observation
from production.aggregation import (
    MIN_RISK_OBSERVATIONS,
    aggregate_series,
    capital_weights,
    chain_link,
    interval_return,
    performance_metrics,
    period_pnl,
    strategy_series,
)
from production.observation import PortfolioManifest

DAY_ONE = datetime(2026, 8, 1, 12, tzinfo=UTC)
MAX_AGE = 172_800


def manifest(*families: str) -> PortfolioManifest:
    return PortfolioManifest.from_mapping(
        {
            "schema_version": 1,
            "portfolio_id": "qf-production",
            "members": [
                {
                    "family": family,
                    "included": True,
                    "account_snapshot_max_age_seconds": MAX_AGE,
                }
                for family in families
            ],
        }
    )


def marks(
    family: str,
    entries: list[tuple[int, str, str]],
) -> list:
    """Build observations as ``(day offset, equity, external flow)`` triples."""
    return [
        observation(
            family=family,
            observed_at=DAY_ONE + timedelta(days=offset),
            equity_usd=Decimal(equity),
            external_flow_usd_since_previous=Decimal(flow),
        )
        for offset, equity, flow in entries
    ]


# --------------------------------------------------------------------------- #
# Core formulas
# --------------------------------------------------------------------------- #


def test_period_pnl_removes_operator_cash() -> None:
    # A $5,000 deposit alongside a $100 gain must read as $100, not $5,100.
    assert period_pnl(Decimal("15100"), Decimal("10000"), Decimal("5000")) == Decimal("100")


def test_period_pnl_removes_withdrawals() -> None:
    assert period_pnl(Decimal("8100"), Decimal("10000"), Decimal("-2000")) == Decimal("100")


def test_interval_return_credits_flow_at_interval_start() -> None:
    assert interval_return(Decimal("15150"), Decimal("10000"), Decimal("5000")) == Decimal("150") / Decimal("15000")


def test_interval_return_is_none_without_a_capital_base() -> None:
    assert interval_return(Decimal("100"), Decimal("0"), Decimal("0")) is None
    assert interval_return(Decimal("100"), Decimal("500"), Decimal("-500")) is None


def test_chain_link_compounds() -> None:
    assert chain_link([Decimal("0.1"), Decimal("0.1")]) == Decimal("0.21")


def test_capital_weights_sum_to_one() -> None:
    weights = capital_weights({"a": Decimal("7500"), "b": Decimal("2500")})
    assert weights == {"a": Decimal("0.75"), "b": Decimal("0.25")}
    assert sum(weights.values()) == Decimal("1")


def test_capital_weights_refuse_a_nonpositive_base() -> None:
    assert capital_weights({"a": Decimal("0")}) == {}


# --------------------------------------------------------------------------- #
# Per-strategy series
# --------------------------------------------------------------------------- #


def test_deposit_does_not_inflate_strategy_pnl() -> None:
    series = strategy_series(
        "example-family",
        marks("example-family", [(0, "10000", "0"), (1, "15100", "5000"), (2, "15200", "0")]),
        max_age_seconds=MAX_AGE,
        now=DAY_ONE + timedelta(days=2, hours=1),
    )
    assert [point.period_pnl_usd for point in series.points] == [
        None,
        Decimal("100"),
        Decimal("100"),
    ]
    assert series.points[-1].cum_pnl_usd == Decimal("200")
    assert series.stale is False


def test_withdrawal_does_not_depress_strategy_pnl() -> None:
    series = strategy_series(
        "example-family",
        marks("example-family", [(0, "10000", "0"), (1, "8100", "-2000")]),
        max_age_seconds=MAX_AGE,
        now=DAY_ONE + timedelta(days=1, hours=1),
    )
    assert series.points[-1].cum_pnl_usd == Decimal("100")
    assert series.points[-1].cum_return == Decimal("100") / Decimal("8000")


def test_inception_mark_claims_no_pnl() -> None:
    series = strategy_series(
        "example-family",
        marks("example-family", [(0, "10000", "0")]),
        max_age_seconds=MAX_AGE,
        now=DAY_ONE + timedelta(hours=1),
    )
    assert series.points[0].period_pnl_usd is None
    assert series.points[0].cum_pnl_usd == Decimal("0")
    assert performance_metrics(series.points).total_return is None


def test_same_day_flows_survive_the_superseded_mark() -> None:
    entries = [
        observation(
            observed_at=DAY_ONE,
            equity_usd=Decimal("10000"),
            external_flow_usd_since_previous=Decimal("0"),
        ),
        observation(
            observed_at=DAY_ONE + timedelta(days=1, hours=1),
            equity_usd=Decimal("13000"),
            external_flow_usd_since_previous=Decimal("3000"),
        ),
        observation(
            observed_at=DAY_ONE + timedelta(days=1, hours=5),
            equity_usd=Decimal("15100"),
            external_flow_usd_since_previous=Decimal("2000"),
        ),
    ]
    series = strategy_series(
        "example-family", entries, max_age_seconds=MAX_AGE, now=DAY_ONE + timedelta(days=1, hours=6)
    )
    assert len(series.points) == 2
    # $5,000 total deposited that day; only $100 is P&L.
    assert series.points[-1].external_flow_usd == Decimal("5000")
    assert series.points[-1].period_pnl_usd == Decimal("100")


def test_absent_capital_is_not_a_zero_series() -> None:
    series = strategy_series("example-family", [], max_age_seconds=MAX_AGE, now=DAY_ONE)
    assert series.has_capital is False
    assert series.equity_usd is None
    assert series.stale is True
    assert series.usable is False


def test_old_mark_reads_stale() -> None:
    series = strategy_series(
        "example-family",
        marks("example-family", [(0, "10000", "0")]),
        max_age_seconds=MAX_AGE,
        now=DAY_ONE + timedelta(days=5),
    )
    assert series.stale is True
    assert series.usable is False


# --------------------------------------------------------------------------- #
# Portfolio aggregation
# --------------------------------------------------------------------------- #


def two_family_series(now: datetime) -> dict:
    return {
        "alpha": strategy_series(
            "alpha",
            marks("alpha", [(0, "7500", "0"), (1, "7600", "0")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
        "beta": strategy_series(
            "beta",
            marks("beta", [(0, "2500", "0"), (1, "2500", "0")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
    }


def test_complete_aggregate_sums_equity_and_weights() -> None:
    now = DAY_ONE + timedelta(days=1, hours=1)
    aggregate = aggregate_series(manifest("alpha", "beta"), two_family_series(now), now=now)
    assert aggregate.completeness == "complete"
    assert aggregate.equity_usd == Decimal("10100")
    assert sum(aggregate.weights.values()) == Decimal("1")
    assert aggregate.points[-1].period_pnl_usd == Decimal("100")
    assert aggregate.points[-1].cum_pnl_usd == Decimal("100")


def test_portfolio_return_is_not_an_average_of_strategy_returns() -> None:
    now = DAY_ONE + timedelta(days=1, hours=1)
    series = two_family_series(now)
    aggregate = aggregate_series(manifest("alpha", "beta"), series, now=now)
    naive_average = (series["alpha"].points[-1].interval_return + series["beta"].points[-1].interval_return) / Decimal(
        "2"
    )
    expected = Decimal("100") / Decimal("10000")
    assert aggregate.points[-1].period_return == expected
    assert aggregate.points[-1].period_return != naive_average


def test_portfolio_return_is_cash_flow_adjusted() -> None:
    now = DAY_ONE + timedelta(days=1, hours=1)
    series = {
        "alpha": strategy_series(
            "alpha",
            marks("alpha", [(0, "7500", "0"), (1, "12600", "5000")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
        "beta": strategy_series(
            "beta",
            marks("beta", [(0, "2500", "0"), (1, "2500", "0")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
    }
    aggregate = aggregate_series(manifest("alpha", "beta"), series, now=now)
    assert aggregate.points[-1].period_pnl_usd == Decimal("100")
    assert aggregate.points[-1].period_return == Decimal("100") / Decimal("15000")


def test_missing_member_makes_the_aggregate_incomplete() -> None:
    now = DAY_ONE + timedelta(days=1, hours=1)
    series = two_family_series(now)
    del series["beta"]
    aggregate = aggregate_series(manifest("alpha", "beta"), series, now=now)
    assert aggregate.completeness == "incomplete"
    assert aggregate.missing_families == ("beta",)
    # The remainder must not be presented as the portfolio total.
    assert aggregate.equity_usd is None
    assert aggregate.weights == {}


def test_stale_member_makes_the_aggregate_stale() -> None:
    now = DAY_ONE + timedelta(days=10)
    aggregate = aggregate_series(manifest("alpha", "beta"), two_family_series(now), now=now)
    assert aggregate.completeness == "stale"
    assert set(aggregate.stale_families) == {"alpha", "beta"}
    assert aggregate.equity_usd is None


def test_no_capital_anywhere_reads_empty() -> None:
    now = DAY_ONE
    aggregate = aggregate_series(
        manifest("example-family"),
        {"example-family": strategy_series("example-family", [], max_age_seconds=MAX_AGE, now=now)},
        now=now,
    )
    assert aggregate.completeness == "empty"
    assert aggregate.points == ()
    assert aggregate.equity_usd is None


def test_gap_day_is_nulled_and_the_next_interval_spans_the_gap() -> None:
    now = DAY_ONE + timedelta(days=2, hours=1)
    series = {
        "alpha": strategy_series(
            "alpha",
            marks("alpha", [(0, "7500", "0"), (1, "7600", "0"), (2, "7700", "0")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
        # beta has no mark on day 1.
        "beta": strategy_series(
            "beta",
            marks("beta", [(0, "2500", "0"), (2, "2600", "0")]),
            max_age_seconds=MAX_AGE,
            now=now,
        ),
    }
    aggregate = aggregate_series(manifest("alpha", "beta"), series, now=now)
    days = {point.day: point for point in aggregate.points}
    gap = days[(DAY_ONE + timedelta(days=1)).date()]
    assert gap.complete is False
    assert gap.missing == ("beta",)
    assert gap.equity_usd is None and gap.cum_pnl_usd is None
    # Alpha's day-1 mark still advanced its own baseline, so the day-2 interval
    # is measured 7600 -> 7700 and 2500 -> 2600, not 7500 -> 7700.
    final = days[(DAY_ONE + timedelta(days=2)).date()]
    assert final.complete is True
    assert final.period_pnl_usd == Decimal("200")
    assert aggregate.completeness == "complete"


# --------------------------------------------------------------------------- #
# Metrics nulls
# --------------------------------------------------------------------------- #


def test_risk_metrics_are_null_below_the_observation_threshold() -> None:
    now = DAY_ONE + timedelta(days=6)
    entries = [(offset, str(10_000 + offset * 10), "0") for offset in range(6)]
    series = strategy_series("example-family", marks("example-family", entries), max_age_seconds=MAX_AGE, now=now)
    metrics = performance_metrics(series.points)
    assert metrics.observation_count == 5
    assert metrics.total_pnl_usd == Decimal("50")
    assert metrics.total_return is not None
    assert metrics.max_drawdown is not None
    assert metrics.positive_day_rate == Decimal("1")
    assert metrics.annualized_volatility is None
    assert metrics.sharpe is None


def test_risk_metrics_appear_once_supported() -> None:
    count = MIN_RISK_OBSERVATIONS + 1
    now = DAY_ONE + timedelta(days=count + 1)
    entries = [(offset, str(10_000 + (offset * 37) % 500), "0") for offset in range(count)]
    series = strategy_series("example-family", marks("example-family", entries), max_age_seconds=MAX_AGE, now=now)
    metrics = performance_metrics(series.points)
    assert metrics.observation_count >= MIN_RISK_OBSERVATIONS
    assert metrics.annualized_volatility is not None
    assert metrics.sharpe is not None
    assert metrics.max_drawdown is not None and metrics.max_drawdown <= 0


def test_no_observations_yields_no_metrics() -> None:
    metrics = performance_metrics(())
    assert metrics.observation_count == 0
    assert metrics.total_pnl_usd is None
    assert metrics.total_return is None
    assert metrics.sharpe is None


@pytest.mark.parametrize("stale_now", [DAY_ONE + timedelta(days=30)])
def test_stale_series_still_reports_its_history(stale_now: datetime) -> None:
    series = strategy_series(
        "example-family",
        marks("example-family", [(0, "10000", "0"), (1, "10100", "0")]),
        max_age_seconds=MAX_AGE,
        now=stale_now,
    )
    assert series.stale is True
    assert performance_metrics(series.points).total_pnl_usd == Decimal("100")
