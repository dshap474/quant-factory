"""Known-answer tests for the explicit canonical intent ledger.

USAGE: uv run pytest packages/platform/backtest/tests/unit/test_intent_ledger.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    materialize_effective_weights,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
    run_intent_ledger,
)
from backtest.errors import BacktestContractError, BacktestUnsupportedFeatureError

from execution import ImmediateMarketPolicy
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Hand-calculated event ledger
# --------------------------------------------------------------------------- #


def _events() -> tuple[pl.DataFrame, pl.DataFrame, list[datetime]]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    times = [base + timedelta(hours=i) for i in range(5)]
    market = pl.DataFrame(
        {"timestamp": times, "kind": ["close", "open", "close", "open", "close"],
         "BTC": [100.0, 100.0, 110.0, 120.0, 130.0]}
    )
    funding = pl.DataFrame({"timestamp": times, "BTC": [0.0, 0.0, 0.01, 0.0, 0.02]})
    return market, funding, times


def _decision(timestamp: datetime, target: float | None, limit: float | None = None) -> StrategyWeights:
    return StrategyWeights(
        weights=pl.DataFrame({"timestamp": [timestamp], "BTC": pl.Series([target], dtype=pl.Float64),
                              "CASH": pl.Series([None if target is None else 1.0 - target], dtype=pl.Float64)}),
        assets=["BTC"], execution=ExecutionTiming.next_bar(),
        quantity_limits=(pl.DataFrame({"timestamp": [timestamp], "BTC": pl.Series([limit], dtype=pl.Float64)})
                         if limit is not None else None),
    )


def test_next_event_fill_hourly_funding_and_frozen_remaining_quantity():
    """Entry 1 BTC, then reduce to 0.5 BTC despite rising fill-time NAV."""
    market, funding, times = _events()
    seen = []

    def decide(timestamp, state):
        seen.append(state)
        return _decision(timestamp, 1.0) if timestamp == times[0] else _decision(timestamp, None, 0.5)

    config = BacktestConfig(
        engine="ledger", initial_capital=100.0, trade_cost_bps=10.0,
        include_funding=True, benchmark="BTC", frequency="hourly", metrics=[],
    )
    result = run_intent_ledger(
        market=market, funding_rates=funding, decision_times=[times[0], times[2]],
        decide=decide, config=config,
    )

    assert [row["nav"] for row in result.account.iter_rows(named=True)] == pytest.approx(
        [100.0, 99.9, 108.8, 118.74, 122.44]
    )
    assert result.account["funding"].to_list() == pytest.approx([0.0, 0.0, -1.1, 0.0, -1.3])
    assert [fill["traded_dollars"] for fill in result.fills] == pytest.approx([100.0, 60.0])
    assert [fill["fee_dollars"] for fill in result.fills] == pytest.approx([0.1, 0.06])
    assert [fill["quantities"]["BTC"] for fill in result.fills] == pytest.approx([1.0, 0.5])
    assert seen[1].nav == pytest.approx(108.8)
    assert seen[1].cash == pytest.approx(-1.2)
    assert seen[1].quantities == {"BTC": 1.0}
    assert result.backtest.engine_meta["accounting"] == "intent_ledger"
    assert result.backtest.to_dataframe().columns == [
        "equity", "benchmark_equity", "price_return", "funding_return",
        "cost_return", "net_return", "turnover",
    ]

    replay = run_intent_ledger(market=market, funding_rates=funding,
                               decisions=result.decisions, config=config)
    assert replay.account.equals(result.account)
    assert replay.fills == result.fills
    assert replay.backtest.to_dataframe().equals(result.backtest.to_dataframe())


def test_forced_exit_prevents_stale_cap_from_reopening():
    market, _, times = _events()
    decisions = StrategyWeights(
        weights=pl.concat([_decision(times[0], 1.0).weights,
                           _decision(times[2], 1.0).weights], how="vertical_relaxed"),
        quantity_limits=pl.DataFrame({"timestamp": [times[0], times[2]], "BTC": [None, 1.0]}),
        assets=["BTC"], execution=ExecutionTiming.next_bar(),
    )
    result = run_intent_ledger(
        market=market, decisions=decisions, forced_exits={times[2]: ["BTC"]},
        relisted_at={times[3]: ["BTC"]},
        config=BacktestConfig(engine="ledger", initial_capital=100.0,
                              trade_cost_bps=0.0, include_funding=False, benchmark="BTC", metrics=[]),
    )
    assert result.fills[1]["kind"] == "forced_exit"
    assert result.fills[1]["quantities"]["BTC"] == 0.0
    assert result.fills[2]["quantities"]["BTC"] == 0.0


def test_ordinary_connector_rejects_extended_intents():
    market, _, times = _events()
    intent = _decision(times[0], None, 0.0)
    with pytest.raises(BacktestUnsupportedFeatureError, match="run_intent_ledger"):
        run_backtest_from_strategy_weights(
            weights=intent, data=market.drop("kind"),
            config=BacktestConfig(engine="ledger"),
        )
    with pytest.raises(BacktestUnsupportedFeatureError, match="run_intent_ledger"):
        materialize_effective_weights(weights=intent, prices=market.drop("kind"))
    with pytest.raises(BacktestUnsupportedFeatureError, match="run_intent_ledger"):
        prepare_execution_from_strategy_weights(
            weights=intent, asset_instruments={}, reference_prices=pl.DataFrame(),
            bars=pl.DataFrame(), instrument_specs=[], execution_calendar=[],
            reporting_times=[], policy=ImmediateMarketPolicy(),
        )


def test_missing_held_quote_fails_closed():
    market, _, times = _events()
    market = market.with_columns(pl.when(pl.col("timestamp") == times[2]).then(None).otherwise(pl.col("BTC")).alias("BTC"))
    with pytest.raises(BacktestContractError, match="missing held mark"):
        run_intent_ledger(
            market=market, decisions=_decision(times[0], 1.0),
            config=BacktestConfig(engine="ledger", initial_capital=100.0,
                                  trade_cost_bps=0.0, include_funding=False, metrics=[]),
        )


def test_callback_mutation_cannot_rewrite_decision_replay():
    market, _, times = _events()
    first = _decision(times[0], 1.0)
    first.metadata["version"] = "frozen"

    def decide(timestamp, state):
        if timestamp == times[0]:
            return first
        first.metadata["version"] = "changed"
        first.weights = _decision(times[0], 0.0).weights
        second = _decision(timestamp, None)
        second.metadata["version"] = "frozen"
        return second

    config = BacktestConfig(engine="ledger", initial_capital=100.0,
                            trade_cost_bps=0.0, include_funding=False,
                            benchmark="BTC", metrics=[])
    result = run_intent_ledger(market=market, decision_times=[times[0], times[2]],
                               decide=decide, config=config)
    assert result.decisions.metadata == {"version": "frozen"}
    assert result.decisions.weights["BTC"][0] == 1.0
    replay = run_intent_ledger(market=market, decisions=result.decisions, config=config)
    assert replay.account.equals(result.account)


def test_daily_attribution_known_answers_and_unchanged_execution():
    """1 BTC entry, funding -1.1/-1.3, half exit; price gain 10+10+5.

    An unheld asset keeps its
    genuine price gap. Attribution must not alter the ordinary account path.
    """
    market, funding, times = _events()
    market = market.with_columns(pl.Series('ALT', [None, 20.0, 20.0, None, None], dtype=pl.Float64))
    funding = funding.with_columns(pl.lit(0.0).alias('ALT'))
    def decide(ts, state):
        one = _decision(ts, 1.0) if ts == times[0] else _decision(ts, None, 0.5)
        one.weights = one.weights.with_columns(pl.lit(0.0).alias('ALT'))
        one.assets = ['BTC', 'ALT']
        if one.quantity_limits is not None:
            one.quantity_limits = one.quantity_limits.with_columns(pl.lit(None, dtype=pl.Float64).alias('ALT'))
        return one
    cfg = BacktestConfig(engine='ledger', initial_capital=100, trade_cost_bps=10,
                         include_funding=True, benchmark='BTC', metrics=[])
    plain = run_intent_ledger(market=market, funding_rates=funding, decide=decide,
                              decision_times=[times[0], times[2]], config=cfg)
    out = run_intent_ledger(market=market, funding_rates=funding, decisions=plain.decisions,
                            config=cfg, collect_attribution=True)
    assert out.account.equals(plain.account)
    assert out.fills == plain.fills
    assert plain.asset_attribution is None
    assert out.asset_attribution is not None
    btc = out.asset_attribution.filter(pl.col('asset') == 'BTC').row(0, named=True)
    assert btc['price_pnl'] == pytest.approx(25)
    assert btc['funding_pnl'] == pytest.approx(-2.4)
    assert btc['fees'] == pytest.approx(0.16)
    assert btc['quantity'] == 0.5
    assert btc['weight'] == pytest.approx(65 / 122.44)
    alt = out.asset_attribution.filter(pl.col('asset') == 'ALT').row(0, named=True)
    assert alt['price'] is None and alt['quantity'] == 0 and alt['weight'] == 0


@pytest.mark.parametrize('target,expected_price,expected_funding', [(1.0, 10.0, -1.1), (-1.0, -10.0, 1.1)])
def test_attribution_daily_boundary_and_terminal_exit(target, expected_price, expected_funding):
    """Buy/short one unit on day one, close at 110 next day, charge both fees."""
    base = datetime(2024, 1, 1, 22, tzinfo=UTC)
    times = [base + timedelta(hours=i) for i in range(4)]
    market = pl.DataFrame({'timestamp': times, 'kind': ['close','open','settlement','close'],
                           'BTC': [100.0,100.0,110.0,110.0]})
    funding = pl.DataFrame({'timestamp': times, 'BTC':[0.0,0.0,0.01,None]})
    result = run_intent_ledger(market=market, funding_rates=funding,
        decisions=_decision(times[0], target), forced_exits={times[2]: ['BTC']},
        config=BacktestConfig(engine='ledger', initial_capital=100, trade_cost_bps=10,
                             benchmark=None, metrics=[]), collect_attribution=True)
    assert result.asset_attribution is not None
    rows = result.asset_attribution.to_dicts()
    assert len(rows) == 2
    assert rows[0]['fees'] == pytest.approx(0.1)
    assert rows[1]['fees'] == pytest.approx(0.11)
    assert rows[1]['price_pnl'] == pytest.approx(expected_price)
    assert rows[1]['funding_pnl'] == pytest.approx(expected_funding)
    assert rows[1]['quantity'] == 0 and rows[1]['price'] == 110.0
    total = sum(r['price_pnl'] + r['funding_pnl'] - r['fees'] for r in rows)
    assert total == pytest.approx(result.account['nav'][-1] - 100)


def test_attribution_does_not_net_long_and_short_asset_cash_flows():
    """$50 long and $50 short: gains $10/$5, funding -$0.6/+$0.9, fees $.05 each."""
    times = [datetime(2024, 1, 1, h, tzinfo=UTC) for h in range(3)]
    market = pl.DataFrame(dict(timestamp=times, kind=['close','open','close'],
                               X=[100.,100.,120.], Y=[50.,50.,45.]))
    funding = pl.DataFrame(dict(timestamp=times, X=[0.,0.,.01], Y=[0.,0.,.02]))
    decisions = StrategyWeights(weights=pl.DataFrame(dict(timestamp=[times[0]], X=[.5], Y=[-.5], CASH=[1.])),
                               assets=['X','Y'], execution=ExecutionTiming.next_bar())
    out = run_intent_ledger(market=market, funding_rates=funding, decisions=decisions,
        config=BacktestConfig(engine='ledger', initial_capital=100, trade_cost_bps=10,
                             benchmark='X', metrics=[]), collect_attribution=True)
    assert out.asset_attribution is not None
    rows = out.asset_attribution.sort('asset')
    assert rows['price_pnl'].to_list() == pytest.approx([10,5])
    assert rows['funding_pnl'].to_list() == pytest.approx([-.6,.9])
    assert rows['fees'].to_list() == pytest.approx([.05,.05])
    assert out.account['nav'][-1] == pytest.approx(115.2)
