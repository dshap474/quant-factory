"""Contract tests for core artifacts and identifiers."""

from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from signals import SignalMetadata, SignalOutput, SignalRunConfig
from strategies import BacktestOutput, StrategyRunConfig, TrainingMetadata


def _sample_equity() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "equity": [1.0, 1.05],
        }
    )


def _sample_predictions() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "prediction": [0.2, 0.4],
        }
    )


def _sample_training_metadata() -> TrainingMetadata:
    return TrainingMetadata(
        data_start="2024-01-01",
        data_end="2024-02-01",
        resolution_minutes=1440,
        n_assets=2,
        asset_list=["BTC", "ETH"],
        train_start="2024-01-01",
        train_end="2024-01-15",
        test_start="2024-01-16",
        test_end="2024-02-01",
        train_rows=10,
        test_rows=5,
        features=["f1", "f2"],
        target="forward_return_30d",
        model_type="xgboost",
        model_params={"max_depth": 4},
    )


def _sample_signal_metadata() -> SignalMetadata:
    return SignalMetadata(
        data_start="2024-01-01",
        data_end="2024-02-01",
        n_samples=100,
        n_features=3,
        feature_list=["f1", "f2", "f3"],
        target="direction_30d",
        model_type="xgboost",
        model_params={"max_depth": 4},
        cv_metrics={"accuracy": 0.55},
    )


class TestIdentifierContracts:
    def test_strategy_id_must_be_canonical(self):
        with pytest.raises(ValueError, match="strategy_id"):
            StrategyRunConfig(strategy_id="BadID", save=False)

    def test_signal_id_must_be_canonical(self):
        with pytest.raises(ValueError, match="signal_id"):
            SignalRunConfig(signal_id="BadID", save=False)


class TestBacktestOutputContracts:
    def test_backtest_output_validates(self, tmp_path):
        output = BacktestOutput(
            strategy_id="test_strategy",
            run_id="run-test-001",
            equity=_sample_equity(),
            metrics={"sharpe": 1.2},
        )
        output.save(tmp_path)

    def test_backtest_output_rejects_bad_id(self):
        output = BacktestOutput(
            strategy_id="BadID",
            run_id="run-test-001",
            equity=_sample_equity(),
            metrics={"sharpe": 1.2},
        )
        with pytest.raises(ValueError, match="strategy_id"):
            output.validate()

    def test_backtest_output_rejects_bad_config(self):
        output = BacktestOutput(
            strategy_id="test_strategy",
            run_id="run-test-001",
            equity=_sample_equity(),
            metrics={"sharpe": 1.2},
            config="bad",  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="config"):
            output.validate()

    def test_backtest_output_roundtrip_with_metadata(self, tmp_path):
        output = BacktestOutput(
            strategy_id="test_strategy",
            run_id="run-test-002",
            equity=_sample_equity(),
            metrics={"sharpe": 1.2},
            config={"foo": "bar"},
            data_range={"start": "2024-01-01", "end": "2024-01-02"},
            training_metadata=_sample_training_metadata(),
        )
        run_dir = output.save(tmp_path / "run")

        loaded = BacktestOutput.from_path(run_dir)
        assert loaded.strategy_id == output.strategy_id
        assert loaded.run_id == output.run_id
        assert loaded.metrics == output.metrics
        assert loaded.data_range == output.data_range
        assert loaded.training_metadata is not None
        assert loaded.training_metadata.model_type == "xgboost"

    def test_training_metadata_rejects_empty_features(self):
        metadata = _sample_training_metadata()
        metadata.features = []
        with pytest.raises(ValueError, match="features"):
            metadata.validate()

    def test_training_metadata_roundtrip(self):
        metadata = _sample_training_metadata()
        loaded = TrainingMetadata.from_dict(metadata.to_dict())
        assert loaded.model_type == metadata.model_type


class TestSignalOutputContracts:
    def test_signal_output_validates(self, tmp_path):
        output = SignalOutput(
            signal_id="test_signal",
            run_id="run-test-001",
            predictions=_sample_predictions(),
            metrics={"accuracy": 0.6},
        )
        output.save(tmp_path)

    def test_signal_output_requires_timestamp(self):
        preds = pl.DataFrame({"prediction": [0.1, 0.2]})
        output = SignalOutput(
            signal_id="test_signal",
            run_id="run-test-001",
            predictions=preds,
            metrics={"accuracy": 0.6},
        )
        with pytest.raises(ValueError, match="timestamp"):
            output.validate()

    def test_signal_output_rejects_bad_config(self):
        output = SignalOutput(
            signal_id="test_signal",
            run_id="run-test-001",
            predictions=_sample_predictions(),
            metrics={"accuracy": 0.6},
            config="bad",  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="config"):
            output.validate()

    def test_signal_output_roundtrip_with_metadata(self, tmp_path):
        output = SignalOutput(
            signal_id="test_signal",
            run_id="run-test-002",
            predictions=_sample_predictions(),
            metrics={"accuracy": 0.6},
            config={"foo": "bar"},
            data_range={"start": "2024-01-01", "end": "2024-01-02"},
            metadata=_sample_signal_metadata(),
        )
        run_dir = output.save(tmp_path)

        loaded = SignalOutput.from_path(run_dir)
        assert loaded.signal_id == output.signal_id
        assert loaded.run_id == output.run_id
        assert loaded.metrics == output.metrics
        assert loaded.data_range == output.data_range
        assert loaded.metadata is not None
        assert loaded.metadata.model_type == "xgboost"

    def test_signal_output_legacy_version_fallback(self, tmp_path):
        run_dir = tmp_path / "signals" / "test_signal" / "v1"
        run_dir.mkdir(parents=True)
        _sample_predictions().write_parquet(run_dir / "predictions.parquet")
        (run_dir / "meta.json").write_text(
            '{"signal_id": "test_signal", "version": "v1", "created_at": "2024-01-01T00:00:00", "metrics": {}, "config": {}}'
        )
        loaded = SignalOutput.from_path(run_dir)
        assert loaded.run_id == "v1"

    def test_signal_metadata_rejects_empty_feature_list(self):
        metadata = _sample_signal_metadata()
        metadata.feature_list = []
        with pytest.raises(ValueError, match="feature_list"):
            metadata.validate()

    def test_signal_metadata_roundtrip(self):
        metadata = _sample_signal_metadata()
        as_dict = metadata.to_dict()
        loaded = SignalMetadata.from_dict(as_dict)
        assert loaded.model_type == metadata.model_type
