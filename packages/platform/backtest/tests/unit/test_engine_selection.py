"""Tests for engine selection (Nautilus default + opt-in ledger)."""

from __future__ import annotations

from backtest import BacktestConfig


def test_default_engine_is_nautilus():
    cfg = BacktestConfig()
    assert cfg.engine == "nautilus"


def test_ledger_engine_is_accepted():
    cfg = BacktestConfig(engine="ledger")
    assert cfg.engine == "ledger"


def test_vectorized_engine_is_rejected():
    try:
        BacktestConfig(engine="vectorized")
    except ValueError as exc:
        assert "Vectorized/auto engines were removed" in str(exc)
        return
    raise AssertionError("Expected BacktestConfig(engine='vectorized') to raise ValueError")


def test_auto_engine_is_rejected():
    try:
        BacktestConfig(engine="auto")
    except ValueError as exc:
        assert "Vectorized/auto engines were removed" in str(exc)
        return
    raise AssertionError("Expected BacktestConfig(engine='auto') to raise ValueError")
