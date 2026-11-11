"""Independent known-answer acceptance for decision-frozen quantity intents.

USAGE: uv run pytest packages/platform/backtest/tests/unit/test_quantity_intents_acceptance.py -q
"""

import json
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from backtest import BacktestConfig, materialize_effective_weights, run_backtest_from_strategy_weights, run_intent_ledger
from backtest.errors import BacktestUnsupportedFeatureError
from strategies import ExecutionTiming, StrategyWeights
from strategies.runner import StrategyRunConfig, StrategyRunner

# --------------------------------------------------------------------------- #
# Small public-contract fixtures
# --------------------------------------------------------------------------- #


def _market():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=i) for i in range(10)]
    prices = [100., 120., 120., 100., 100., 110., 110., 130., 130., 90.]
    return pl.DataFrame({"timestamp": times, "kind": ["open"] * 10, "BTC": prices}), times


def _intent(ts, quantity, *, weight=None, limit=None):
    return StrategyWeights(
        weights=pl.DataFrame({"timestamp": [ts], "BTC": pl.Series([weight], dtype=pl.Float64),
                              "CASH": pl.Series([None if weight is None else 1 - weight], dtype=pl.Float64)}),
        assets=["BTC"], execution=ExecutionTiming.next_bar(),
        quantity_targets=pl.DataFrame({"timestamp": [ts], "BTC": pl.Series([quantity], dtype=pl.Float64)}),
        quantity_limits=None if limit is None else pl.DataFrame({"timestamp": [ts], "BTC": [limit]}),
    )


def _config(fee=100.):
    return BacktestConfig(engine="ledger", initial_capital=1000., trade_cost_bps=fee,
                          include_funding=False, benchmark="BTC", metrics=[])


# --------------------------------------------------------------------------- #
# Frozen quantities, accounting, and persistence
# --------------------------------------------------------------------------- #


def test_callback_frozen_targets_accounting_and_exact_replay(tmp_path):
    market, times = _market()
    def decide(ts, state):
        target = {times[0]: 4., times[2]: 10., times[6]: None, times[8]: 0.}.get(ts)
        if ts == times[4]:
            target = state.quantities["BTC"] - 2.
        return _intent(ts, target)

    result = run_intent_ledger(market=market, decision_times=times[::2], decide=decide, config=_config())
    fills = {f["timestamp"]: f for f in result.fills}
    expected_q = [4., 4. + 515.2 / 101., 2. + 515.2 / 101.]
    for ts, quantity, traded, fee in zip(
        [times[1], times[3], times[5], times[9]],
        [*expected_q, 0.],
        [480., 51520. / 101., 220., expected_q[2] * 90.],
        [4.8, 515.2 / 101., 2.2, expected_q[2] * .9],
        strict=True,
    ):
        fill = fills[ts]
        assert fill["quantities"]["BTC"] == pytest.approx(quantity)
        assert fill["traded_dollars"] == pytest.approx(traded)
        assert fill["fee_dollars"] == pytest.approx(fee)
    # A hold may be recorded as a zero fill or omitted entirely.
    if times[7] in fills:
        assert fills[times[7]]["traded_dollars"] == 0.
        assert fills[times[7]]["fee_dollars"] == 0.
    assert result.account["cash"].min() >= -1e-9  # ty: ignore[unsupported-operator]
    assert result.account["cash"][1] == pytest.approx(515.2)
    assert result.account["cash"][5] == pytest.approx(217.8)
    assert result.backtest.to_dataframe().columns == ["equity", "benchmark_equity", "price_return", "funding_return", "cost_return", "net_return", "turnover"]

    path = tmp_path / "decisions.parquet"
    result.decisions.save(path)
    loaded = StrategyWeights.from_parquet(path)
    rebuilt = StrategyWeights.concat([loaded.slice(i) for i in range(5)])
    assert rebuilt.quantity_targets is not None and result.decisions.quantity_targets is not None
    assert rebuilt.quantity_targets.equals(result.decisions.quantity_targets)
    replay = run_intent_ledger(market=market, decisions=rebuilt, config=_config())
    assert replay.account.equals(result.account)
    assert replay.fills == result.fills
    assert replay.backtest.to_dataframe().equals(result.backtest.to_dataframe())

    costlier = run_intent_ledger(market=market, decisions=rebuilt, config=_config(200.))
    assert costlier.decisions.quantity_targets is not None
    assert costlier.decisions.quantity_targets.equals(result.decisions.quantity_targets)
    assert costlier.fills[0]["quantities"]["BTC"] == pytest.approx(4.)
    assert costlier.fills[1]["quantities"]["BTC"] == pytest.approx(4. + 510.4 / 102.)
    assert costlier.account["cash"].min() >= -1e-9  # ty: ignore[unsupported-operator]


def test_old_weight_artifact_and_behavior_remain_unchanged(tmp_path):
    market, times = _market()
    old = StrategyWeights(weights=pl.DataFrame({"timestamp": [times[0]], "BTC": [1.], "CASH": [0.]}), assets=["BTC"])
    path = tmp_path / "old.parquet"
    # Explicitly remove the extension key, reproducing a pre-extension artifact.
    # Use the old writer now, then remove any future extension key from its stored metadata.
    old.save(path)
    metadata = json.loads(pl.read_parquet_metadata(path)["strategy_weights"])
    metadata.pop("quantity_targets", None)
    old.weights.write_parquet(path, metadata={"strategy_weights": json.dumps(metadata)})
    loaded = StrategyWeights.from_parquet(path)
    out = run_intent_ledger(market=market, decisions=loaded, config=_config())
    assert out.fills[0]["quantities"]["BTC"] == pytest.approx(1000. / 120.)
    assert out.account["cash"][1] == pytest.approx(-10.)
    mixed = StrategyWeights.concat([loaded, _intent(times[2], 2.)])
    assert mixed.quantity_targets is not None
    assert mixed.quantity_targets["BTC"].to_list() == [None, 2.]


# --------------------------------------------------------------------------- #
# Invalid and unsupported contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [-1., float("inf"), float("nan")])
def test_invalid_quantities_fail_closed(value):
    _, times = _market()
    with pytest.raises((ValueError, TypeError)):
        _intent(times[0], value).validate()


def test_conflicting_weight_and_limit_fail_closed():
    _, times = _market()
    for kwargs in ({"weight": 0.5}, {"limit": 0.5}):
        with pytest.raises(ValueError):
            _intent(times[0], 1., **kwargs).validate()


def test_misaligned_quantity_frame_fails_closed():
    _, times = _market()
    with pytest.raises(ValueError):
        StrategyWeights(weights=pl.DataFrame({"timestamp": [times[0]], "BTC": [None], "CASH": [None]}),
                        assets=["BTC"], quantity_targets=pl.DataFrame({"timestamp": [times[1]], "BTC": [1.]})).validate()


def test_ordinary_adapters_reject_quantity_targets():
    market, times = _market()
    intent = _intent(times[0], 1.)
    with pytest.raises(BacktestUnsupportedFeatureError):
        materialize_effective_weights(weights=intent, prices=market.drop("kind"))
    with pytest.raises(BacktestUnsupportedFeatureError):
        run_backtest_from_strategy_weights(weights=intent, data=market.drop("kind"), config=_config())


def test_forced_exit_blocks_pending_quantity_and_relisting_does_not_replay_it():
    market, times = _market()
    decisions = StrategyWeights.concat([_intent(times[0], 3.), _intent(times[1], 5.), _intent(times[4], 2.)])
    out = run_intent_ledger(market=market, decisions=decisions, forced_exits={times[2]: ["BTC"]},
                            relisted_at={times[4]: ["BTC"]}, config=_config())
    assert out.fills[1]["quantities"]["BTC"] == 0.
    assert out.fills[-1]["quantities"]["BTC"] == pytest.approx(2.)


def test_quantity_target_rejects_existing_negative_cash():
    market, times = _market()
    old = StrategyWeights(weights=pl.DataFrame({"timestamp": [times[0]], "BTC": [1.], "CASH": [0.]}), assets=["BTC"])
    decisions = StrategyWeights.concat([old, _intent(times[2], 9.)])
    with pytest.raises((ValueError, RuntimeError, BacktestUnsupportedFeatureError)):
        run_intent_ledger(market=market, decisions=decisions, config=_config())


def test_quantity_mode_rejects_multiple_risky_assets():
    _, times = _market()
    market = pl.DataFrame({"timestamp": times, "kind": ["open"] * len(times),
                           "BTC": [100.] * len(times), "ETH": [50.] * len(times)})
    with pytest.raises((ValueError, BacktestUnsupportedFeatureError)):
        intent = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [times[0]], "BTC": [None], "ETH": [None], "CASH": [None]}),
            assets=["BTC", "ETH"],
            quantity_targets=pl.DataFrame({"timestamp": [times[0]], "BTC": [1.], "ETH": [None]}),
        )
        intent.validate()
        run_intent_ledger(market=market, decisions=intent, config=_config())


def test_quantity_mode_rejects_existing_short_holding():
    market, times = _market()
    short = StrategyWeights(weights=pl.DataFrame({"timestamp": [times[0]], "BTC": [-0.5], "CASH": [1.5]}),
                            assets=["BTC"])
    with pytest.raises((ValueError, RuntimeError, BacktestUnsupportedFeatureError)):
        decisions = StrategyWeights.concat([short, _intent(times[2], 1.)])
        run_intent_ledger(market=market, decisions=decisions, config=_config())


@pytest.mark.parametrize("bad_quote", [None, 0., -1., float("inf"), float("nan")])
def test_quantity_target_rejects_invalid_execution_quote(bad_quote):
    market, times = _market()
    prices = market["BTC"].to_list()
    prices[1] = bad_quote
    market = market.with_columns(pl.Series("BTC", prices, dtype=pl.Float64))
    with pytest.raises((ValueError, RuntimeError)):
        run_intent_ledger(market=market, decisions=_intent(times[0], 1.), config=_config())


def test_runner_identity_stamping_preserves_quantity_target():
    _, times = _market()
    class Runner(StrategyRunner):
        def load_data(self):
            return pl.DataFrame({"timestamp": [times[0]]})
        def generate_weights(self, data):
            return _intent(times[0], 3.)
        def get_config_dict(self):
            return {}

    runner = Runner(StrategyRunConfig(strategy_id="acceptance", strategy_type="acceptance", memory_version="v001", save=False))
    result = runner.decide_history(runner.load_data())
    assert (result.strategy_id, result.version) == ("acceptance", "v001")
    assert result.quantity_targets is not None
    assert result.quantity_targets["BTC"].to_list() == [3.]
