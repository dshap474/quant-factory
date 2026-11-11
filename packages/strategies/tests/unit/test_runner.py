"""Unit tests for StrategyRunner."""

import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest

from strategies import AccountState, StrategyRunConfig, StrategyRunner, StrategyRunResult, StrategyWeights


# Create mock modules for backtest and results packages
# These are sibling packages that may not be available in all test environments
def _create_mock_backtest_module():
    """Create a mock backtest module."""
    mock_module = MagicMock()
    mock_module.BacktestConfig = MagicMock
    mock_module.run_backtest = MagicMock()
    mock_module.run_backtest_from_strategy_weights = mock_module.run_backtest
    mock_module.materialize_effective_weights.side_effect = lambda *, weights, prices: weights
    return mock_module


class SimpleTestRunner(StrategyRunner):
    """Simple test implementation of StrategyRunner."""

    def __init__(
        self,
        data: pl.DataFrame,
        signal: list[float],
        save: bool = False,
        db_root: Path | None = None,
    ):
        config = StrategyRunConfig(
            strategy_id="test_strategy",
            strategy_type="test-family",
            save=save,
            db_root=db_root or Path("/tmp/test_db"),
            memory_version="v001",
        )
        super().__init__(config)
        self._data = data
        self._signal = signal

    def load_data(self) -> pl.DataFrame:
        return self._data

    def generate_weights(self, data: pl.DataFrame) -> StrategyWeights:
        # Simple signal-to-weights conversion
        weights_df = pl.DataFrame({
            "timestamp": data["timestamp"],
            "BTC": self._signal,
            "CASH": [1.0 - s for s in self._signal],
        })
        return StrategyWeights(weights=weights_df, assets=["BTC"])

    def get_config_dict(self) -> dict[str, Any]:
        return {"signal": self._signal}


class TestStrategyRunConfig:
    """Tests for StrategyRunConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = StrategyRunConfig(strategy_id="test")
        assert config.strategy_id == "test"
        assert config.save is True
        assert config.backtest_config is None

    def test_custom_db_root(self, tmp_path):
        """Test custom db_root."""
        config = StrategyRunConfig(
            strategy_id="test",
            db_root=tmp_path,
        )
        assert config.db_root == tmp_path


class TestStrategyRunner:
    """Tests for StrategyRunner base class."""

    @pytest.fixture
    def sample_data(self):
        """Create sample price data."""
        return pl.DataFrame({
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
                datetime(2024, 1, 4),
                datetime(2024, 1, 5),
            ],
            "BTC": [100.0, 110.0, 105.0, 115.0, 120.0],
            "CASH": [1.0, 1.0, 1.0, 1.0, 1.0],
        })

    def test_abstract_methods_required(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            StrategyRunner(StrategyRunConfig(strategy_id="test"))

    def test_account_feedback_is_defensively_copied_and_legacy_runner_fails_explicitly(self, sample_data):
        quantities = {"BTC": 1.0}
        state = AccountState(
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            quantities=quantities,
            nav=100.0,
            weights={"BTC": 0.5},
            cash=50.0,
        )
        quantities["BTC"] = 5.0
        assert state.quantities["BTC"] == 1.0
        runner = SimpleTestRunner(data=sample_data, signal=[0.5] * 5)
        assert runner.decide().n_timestamps == 5
        with pytest.raises(NotImplementedError, match="does not support account_state"):
            runner.decide(state)

    def test_decide_stamps_runner_identity(self, sample_data):
        runner = SimpleTestRunner(data=sample_data, signal=[0.5] * 5)
        runner.run_config.memory_version = "v003"
        decision = runner.decide()
        assert (decision.strategy_id, decision.version) == ("test_strategy", "v003")

        conflicting = SimpleTestRunner(data=sample_data, signal=[0.5] * 5)
        original = conflicting.generate_weights
        conflicting.generate_weights = lambda data: replace(original(data), strategy_id="other")
        with pytest.raises(ValueError, match="conflicts with runner"):
            conflicting.decide()

    def test_account_feedback_requires_utc(self):
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            AccountState(
                timestamp=datetime(2024, 1, 1),
                quantities={},
                nav=100.0,
                weights={},
                cash=100.0,
            )

    def test_generate_weights_validation(self, sample_data):
        """Test that run() validates weights."""
        # Create runner with invalid weights (don't sum to 1)
        class BadRunner(StrategyRunner):
            def load_data(self):
                return sample_data

            def generate_weights(self, data):
                weights_df = pl.DataFrame({
                    "timestamp": data["timestamp"],
                    "BTC": [0.5] * len(data),
                    "CASH": [0.3] * len(data),  # Sums to 0.8
                })
                return StrategyWeights(weights=weights_df, assets=["BTC"])

            def get_config_dict(self):
                return {}

        runner = BadRunner(StrategyRunConfig(strategy_id="bad", save=False))

        with pytest.raises(ValueError, match="sum to 1.0"):
            runner.run()

    def test_run_without_save(self, sample_data, tmp_path):
        """Test running without saving."""
        # Create mock backtest module
        mock_backtest_module = _create_mock_backtest_module()

        # Create mock backtest result
        mock_result = MagicMock()
        mock_result.metrics = {"sharpe": 1.5, "max_drawdown": 0.1}
        mock_result.to_dataframe.return_value = pl.DataFrame({
            "equity": [1.0, 1.1, 1.05, 1.15, 1.2],
        })
        mock_result.summary.return_value = "Mock Summary"
        mock_backtest_module.run_backtest.return_value = mock_result

        # Patch sys.modules before import
        original_backtest = sys.modules.get("backtest")
        sys.modules["backtest"] = mock_backtest_module

        try:
            runner = SimpleTestRunner(
                data=sample_data,
                signal=[0.5, 0.6, 0.4, 0.7, 0.5],
                save=False,
                db_root=tmp_path,
            )

            result = runner.run()

            assert result.run_id is None
            assert result.run_dir is None
            assert result.metrics["sharpe"] == 1.5
            assert isinstance(result.weights, StrategyWeights)
        finally:
            # Restore original module
            if original_backtest is not None:
                sys.modules["backtest"] = original_backtest
            else:
                sys.modules.pop("backtest", None)

    def test_run_with_save(self, sample_data, tmp_path):
        """Test running with save enabled."""
        mock_backtest_module = _create_mock_backtest_module()

        # Create mock backtest result
        mock_result = MagicMock()
        mock_result.metrics = {"sharpe": 1.5}
        mock_result.to_dataframe.return_value = pl.DataFrame({
            "equity": [1.0, 1.1, 1.05, 1.15, 1.2],
        })
        mock_result.summary.return_value = "Mock Summary"
        mock_backtest_module.run_backtest.return_value = mock_result

        # Patch sys.modules before import
        original_backtest = sys.modules.get("backtest")

        sys.modules["backtest"] = mock_backtest_module

        try:
            runner = SimpleTestRunner(
                data=sample_data,
                signal=[0.5, 0.6, 0.4, 0.7, 0.5],
                save=True,
                db_root=tmp_path,
            )

            result = runner.run()

            assert result.run_id is not None
            assert result.run_id.startswith("run-")
            assert result.run_dir is not None
            assert result.run_dir == tmp_path / "research/strategies/test-family/v001/test_strategy" / result.run_id
            for name in ("decisions.parquet", "backtest.parquet", "meta.json"):
                assert (result.run_dir / name).exists()
            assert StrategyWeights.from_parquet(result.run_dir / "decisions.parquet").version == "v001"
        finally:
            # Restore original modules
            if original_backtest is not None:
                sys.modules["backtest"] = original_backtest
            else:
                sys.modules.pop("backtest", None)

    def test_data_to_prices_wide_format(self, sample_data):
        """Test _data_to_prices with already-wide data."""
        runner = SimpleTestRunner(
            data=sample_data,
            signal=[0.5] * 5,
            save=False,
        )

        prices = runner._data_to_prices(sample_data, ["BTC"], "CASH")
        assert "timestamp" in prices.columns
        assert "BTC" in prices.columns
        assert "CASH" in prices.columns

    def test_data_to_prices_panel_format(self):
        """Test _data_to_prices with panel format data."""
        panel_data = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 2)],
            "asset": ["BTC", "ETH", "BTC", "ETH"],
            "close": [100.0, 50.0, 110.0, 55.0],
        })

        runner = SimpleTestRunner(
            data=panel_data,
            signal=[0.5, 0.5],
            save=False,
        )

        prices = runner._data_to_prices(panel_data, ["BTC", "ETH"], "CASH")
        assert "timestamp" in prices.columns
        assert "BTC" in prices.columns
        assert "ETH" in prices.columns
        assert "CASH" in prices.columns
        assert len(prices) == 2  # 2 unique timestamps

    def test_get_config_dict(self, sample_data):
        """Test get_config_dict returns expected format."""
        runner = SimpleTestRunner(
            data=sample_data,
            signal=[0.5, 0.6, 0.4, 0.7, 0.5],
            save=False,
        )

        config = runner.get_config_dict()
        assert "signal" in config
        assert config["signal"] == [0.5, 0.6, 0.4, 0.7, 0.5]

    def test_build_backtest_output_uses_effective_timestamps_for_sparse_schedule(self, sample_data):
        """Test persisted backtest output uses the effective schedule when equity drops the first row."""
        runner = SimpleTestRunner(
            data=sample_data,
            signal=[0.5] * 5,
            save=False,
        )
        weights = StrategyWeights(
            weights=pl.DataFrame({
                "timestamp": sample_data["timestamp"][1:],
                "BTC": [0.5, 0.5, 0.5, 0.5],
                "CASH": [0.5, 0.5, 0.5, 0.5],
            }),
            assets=["BTC"],
        )
        mock_result = MagicMock()
        mock_result.metrics = {"sharpe": 1.0}
        mock_result.to_dataframe.return_value = pl.DataFrame({
            "equity": [1.0, 1.1, 1.2],
            "benchmark_equity": [1.0, 1.0, 1.0],
            "price_return": [0.0, 0.1, 0.09],
            "funding_return": [0.0, 0.0, 0.0],
            "cost_return": [0.0, 0.0, 0.0],
            "net_return": [0.0, 0.1, 0.09],
            "turnover": [0.0, 0.0, 0.0],
        })

        output = runner._build_backtest_output(weights, mock_result, "run-test")

        assert output.equity["timestamp"].to_list() == sample_data["timestamp"][2:].to_list()


class TestStrategyRunResult:
    """Tests for StrategyRunResult."""

    def test_defaults_effective_weights(self):
        """Test StrategyRunResult defaults effective weights to decision weights."""
        mock_backtest = MagicMock()
        weights = StrategyWeights(
            weights=pl.DataFrame({
                "timestamp": [datetime(2024, 1, 1)],
                "BTC": [0.5],
                "CASH": [0.5],
            }),
            assets=["BTC"],
        )

        result = StrategyRunResult(
            weights=weights,
            backtest=mock_backtest,
            metrics={"sharpe": 1.0},
            config={},
        )

        assert result.effective_weights == weights

    def test_summary(self):
        """Test summary method."""
        mock_backtest = MagicMock()
        mock_backtest.summary.return_value = "Backtest Summary"
        mock_backtest.metrics = {"sharpe": 1.5}

        weights = StrategyWeights(
            weights=pl.DataFrame({
                "timestamp": [datetime(2024, 1, 1)],
                "BTC": [0.5],
                "CASH": [0.5],
            }),
            assets=["BTC"],
        )

        result = StrategyRunResult(
            weights=weights,
            effective_weights=weights,
            backtest=mock_backtest,
            metrics={"sharpe": 1.5},
            config={"test": True},
            run_id="run-123",
        )

        summary = result.summary()
        assert "run-123" in summary
        assert "Backtest Summary" in summary
