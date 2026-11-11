"""Independent hand-ledger acceptance through the shared intent execution API.

USAGE: uv run pytest packages/strategies/tests/test_intent_execution.py -q
Expected dollar balances below are hand-derived from q*p, signed funding,
and fees on absolute traded notional. No family engine supplies the oracle.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Tiny event grids and canonical instructions
# --------------------------------------------------------------------------- #
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from backtest import BacktestConfig, run_intent_ledger

from strategies import StrategyWeights

T = datetime(2025, 1, 1, tzinfo=UTC)
TIMES = [T + timedelta(hours=i) for i in range(5)]


def intent(at, a, b, cap=None):
    cash = None if a is None or b is None else 1.0 - a - b
    return StrategyWeights(
        weights=pl.DataFrame(
            {"timestamp": [at], "A": [a], "B": [b], "CASH": [cash]},
            schema_overrides={x: pl.Float64 for x in ("A", "B", "CASH")},
        ),
        assets=["A", "B"],
        metadata={"strategy_id": "independent_hand_ledger"},
        quantity_limits=None
        if cap is None
        else pl.DataFrame(
            {"timestamp": [at], "A": [cap], "B": [None]}, schema_overrides={"A": pl.Float64, "B": pl.Float64}
        ),
    )


def config(cost=0):
    return BacktestConfig(engine="ledger", initial_capital=1000, trade_cost_bps=cost, benchmark="B", metrics=[])


def test_long_short_funding_fees_caps_and_saved_replay(tmp_path):
    market = pl.DataFrame(
        {
            "timestamp": TIMES,
            "kind": ["close", "open", "close", "open", "close"],
            "A": [100.0, 50.0, 60.0, 120.0, 110.0],
            "B": [100.0, 100.0, 80.0, 60.0, 70.0],
        }
    )
    funding = pl.DataFrame({"timestamp": TIMES, "A": [0.0, 0.0, 0.01, 0.0, 0.001], "B": [0.0, 0.0, 0.02, 0.0, 0.0]})
    states = []

    def decide(at, state):
        states.append(state)
        return intent(at, 0.5, -0.2) if at == TIMES[0] else intent(at, None, 0.0, 8.0)

    result = run_intent_ledger(
        market=market, funding_rates=funding, decision_times=[TIMES[0], TIMES[2]], decide=decide, config=config(10)
    )
    assert result.fills[0]["quantities"] == {"A": 10.0, "B": -2.0}
    assert states[1].nav == pytest.approx(1136.5, abs=1e-10)
    assert result.fills[1]["quantities"] == {"A": 8.0, "B": 0.0}
    assert result.account["cash"][-1] == pytest.approx(815.26, abs=1e-10)
    assert result.account["nav"][-1] == pytest.approx(1695.26, abs=1e-10)
    assert result.account["funding"].sum() == pytest.approx(-3.68, abs=1e-10)
    assert result.account["fee"].sum() == pytest.approx(1.06, abs=1e-10)
    path = tmp_path / "decisions.parquet"
    result.decisions.save(path)
    replay = run_intent_ledger(
        market=market, funding_rates=funding, decisions=StrategyWeights.from_parquet(path), config=config(10)
    )
    assert replay.account.equals(result.account)
    assert replay.fills == result.fills


@pytest.mark.parametrize("sign", [1.0, -1.0])
@pytest.mark.parametrize("second_target", [None, 2.0, -2.0])
def test_limit_is_in_contract_units_and_never_flips(sign, second_target):
    market = pl.DataFrame(
        {
            "timestamp": TIMES[:4],
            "kind": ["close", "open", "close", "open"],
            "A": [100.0, 50.0, 50.0, 75.0],
            "B": [100.0] * 4,
        }
    )

    def decide(at, state):
        return intent(at, sign * 0.5, 0.0) if at == TIMES[0] else intent(at, second_target, None, sign * 8.0)

    result = run_intent_ledger(market=market, decision_times=[TIMES[0], TIMES[2]], decide=decide, config=config())
    same_sign = second_target is None or second_target * sign > 0
    assert result.fills[-1]["quantities"]["A"] == (sign * 8 if same_sign else 0.0)


def test_scheduled_limit_cannot_undo_forced_exit():
    market = pl.DataFrame(
        {
            "timestamp": TIMES[:4],
            "kind": ["close", "open", "close", "open"],
            "A": [100.0, 50.0, 50.0, 75.0],
            "B": [100.0] * 4,
        }
    )

    def decide(at, state):
        return intent(at, 0.5, 0.0) if at == TIMES[0] else intent(at, 2.0, None, 8.0)

    result = run_intent_ledger(
        market=market,
        decision_times=[TIMES[0], TIMES[2]],
        decide=decide,
        forced_exits={TIMES[3]: ["A"]},
        config=config(),
    )
    assert result.fills[-1]["quantities"]["A"] == 0.0


def test_flat_zero_cap_requires_no_nonexistent_execution_quote():
    market = pl.DataFrame(
        {"timestamp": TIMES[:2], "kind": ["close", "open"], "A": [None, None], "B": [100.0, 100.0]},
        schema_overrides={"A": pl.Float64},
    )
    result = run_intent_ledger(
        market=market, decision_times=[TIMES[0]], decide=lambda at, state: intent(at, 1.0, 0.0, 0.0), config=config()
    )
    assert result.fills[0]["quantities"]["A"] == 0.0
    assert result.account["nav"][-1] == 1000.0


def test_future_prices_do_not_change_earlier_feedback():
    def run(last_price):
        market = pl.DataFrame(
            {
                "timestamp": TIMES[:4],
                "kind": ["close", "open", "close", "open"],
                "A": [100.0, 50.0, 60.0, last_price],
                "B": [100.0] * 4,
            }
        )
        observed = []

        def decide(at, state):
            observed.append((at, state.nav, dict(state.quantities)))
            return intent(at, 0.5, 0.0) if at == TIMES[0] else intent(at, None, None, 8.0)

        run_intent_ledger(market=market, decision_times=[TIMES[0], TIMES[2]], decide=decide, config=config())
        return observed

    assert run(75.0) == run(750.0)
