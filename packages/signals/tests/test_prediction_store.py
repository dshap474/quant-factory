"""Boundary tests for the signals-owned ``PredictionStore``."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from signals import PredictionStore

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def temp_signals_dir(tmp_path: Path) -> Path:
    """Create a temporary signals directory."""
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    return signals_dir


@pytest.fixture
def store(temp_signals_dir: Path) -> PredictionStore:
    """Create a prediction store for a test."""
    return PredictionStore(temp_signals_dir)


@pytest.fixture
def sample_predictions() -> pl.DataFrame:
    """Create a representative single-asset prediction frame."""
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
            ],
            "signal_name": ["test_signal"] * 3,
            "model_id": ["run-0001"] * 3,
            "prediction": [0.65, 0.72, 0.58],
            "predicted_at": [datetime.now()] * 3,
        }
    )


# --------------------------------------------------------------------------- #
# Initialization and persistence
# --------------------------------------------------------------------------- #

class TestPredictionStoreInit:
    """Tests for prediction store initialization."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """The store creates a missing signals directory."""
        signals_dir = tmp_path / "new_signals"
        assert not signals_dir.exists()

        store = PredictionStore(signals_dir)

        assert signals_dir.exists()
        assert store.signals_dir == signals_dir

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """The store accepts string paths."""
        store = PredictionStore(str(tmp_path / "signals"))
        assert isinstance(store.signals_dir, Path)


class TestPredictionStoreSave:
    """Tests for ``PredictionStore.save``."""

    def test_save_new_signal(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Saving a new signal writes its parquet history."""
        path = store.save(sample_predictions, "test_signal")

        assert path.exists()
        assert path.name == "predictions.parquet"
        saved = pl.read_parquet(path)
        assert len(saved) == 3
        assert saved["prediction"].to_list() == [0.65, 0.72, 0.58]

    def test_save_creates_latest_json(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Saving writes latest-row metadata."""
        store.save(sample_predictions, "test_signal")

        latest_path = store.signals_dir / "test_signal" / "latest.json"
        assert latest_path.exists()
        latest = json.loads(latest_path.read_text())
        assert "timestamp" in latest
        assert latest["prediction"] == 0.58

    def test_save_creates_index_json(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Saving writes aggregate index metadata."""
        store.save(sample_predictions, "test_signal")

        index_path = store.signals_dir / "test_signal" / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert index["row_count"] == 3
        assert "date_range" in index
        assert "model_ids" in index

    def test_save_with_metadata(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Save metadata is available from the latest record."""
        metadata = {"experiment": "test", "version": 1}
        store.save(sample_predictions, "test_signal", metadata)

        latest = store.get_latest("test_signal")
        assert latest is not None
        assert latest["metadata"] == metadata

    def test_save_append_deduplicates(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Overlapping single-asset saves keep the newest prediction."""
        store.save(sample_predictions, "test_signal")
        new_predictions = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 3), datetime(2024, 1, 4)],
                "signal_name": ["test_signal"] * 2,
                "model_id": ["run-0002"] * 2,
                "prediction": [0.60, 0.75],
                "predicted_at": [datetime.now()] * 2,
            }
        )
        store.save(new_predictions, "test_signal")

        history = store.get_history("test_signal")
        assert len(history) == 4
        jan3 = history.filter(pl.col("timestamp") == datetime(2024, 1, 3))
        assert jan3["model_id"][0] == "run-0002"

    def test_save_append_deduplicates_by_timestamp_and_asset(self, store: PredictionStore) -> None:
        """Cross-sectional saves deduplicate on timestamp and asset."""
        base = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1)],
                "asset": ["BTC", "ETH"],
                "signal_name": ["test_signal", "test_signal"],
                "model_id": ["run-0001", "run-0001"],
                "prediction": [0.10, 0.20],
                "predicted_at": [datetime(2024, 1, 1), datetime(2024, 1, 1)],
            }
        )
        store.save(base, "test_signal")
        update = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "asset": ["BTC", "ETH"],
                "signal_name": ["test_signal", "test_signal"],
                "model_id": ["run-0002", "run-0002"],
                "prediction": [0.30, 0.40],
                "predicted_at": [datetime(2024, 1, 1, 1), datetime(2024, 1, 2, 1)],
            }
        )
        store.save(update, "test_signal")

        history = store.get_history("test_signal")
        assert len(history) == 3
        btc_jan1 = history.filter(
            (pl.col("timestamp") == datetime(2024, 1, 1)) & (pl.col("asset") == "BTC")
        )
        eth_jan1 = history.filter(
            (pl.col("timestamp") == datetime(2024, 1, 1)) & (pl.col("asset") == "ETH")
        )
        assert btc_jan1["model_id"][0] == "run-0002"
        assert eth_jan1["model_id"][0] == "run-0001"


# --------------------------------------------------------------------------- #
# Queries and metadata
# --------------------------------------------------------------------------- #

class TestPredictionStoreGetHistory:
    """Tests for ``PredictionStore.get_history``."""

    def test_get_full_history(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Full history is sorted by timestamp."""
        store.save(sample_predictions, "test_signal")
        history = store.get_history("test_signal")
        assert len(history) == 3
        assert history["timestamp"].is_sorted()

    def test_get_history_with_date_range(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Date filters are inclusive."""
        store.save(sample_predictions, "test_signal")
        history = store.get_history("test_signal", start_date="2024-01-02", end_date="2024-01-02")
        assert len(history) == 1
        assert history["prediction"][0] == 0.72

    def test_get_history_signal_not_found(self, store: PredictionStore) -> None:
        """Missing signal history raises ``KeyError``."""
        with pytest.raises(KeyError, match="No predictions found"):
            store.get_history("nonexistent_signal")


class TestPredictionStoreGetLatest:
    """Tests for ``PredictionStore.get_latest``."""

    def test_get_latest(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Latest returns the most recent saved row."""
        store.save(sample_predictions, "test_signal")
        latest = store.get_latest("test_signal")
        assert latest is not None
        assert latest["prediction"] == 0.58
        assert "timestamp" in latest

    def test_get_latest_not_found(self, store: PredictionStore) -> None:
        """Missing latest metadata returns ``None``."""
        assert store.get_latest("nonexistent_signal") is None


class TestPredictionStoreListSignals:
    """Tests for ``PredictionStore.list_signals``."""

    def test_list_signals_empty(self, store: PredictionStore) -> None:
        """An empty store lists no signals."""
        assert store.list_signals() == []

    def test_list_signals(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Signal names are sorted and include only persisted signals."""
        store.save(sample_predictions.with_columns(pl.lit("signal_a").alias("signal_name")), "signal_a")
        store.save(sample_predictions.with_columns(pl.lit("signal_b").alias("signal_name")), "signal_b")
        assert store.list_signals() == ["signal_a", "signal_b"]


class TestPredictionStoreGetSignalInfo:
    """Tests for ``PredictionStore.get_signal_info``."""

    def test_get_signal_info(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Signal info includes row and model counts."""
        store.save(sample_predictions, "test_signal")
        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["row_count"] == 3
        assert "date_range" in info
        assert info["model_ids"] == ["run-0001"]

    def test_get_signal_info_not_found(self, store: PredictionStore) -> None:
        """Missing signal info returns ``None``."""
        assert store.get_signal_info("nonexistent_signal") is None


class TestPredictionStoreDeleteSignal:
    """Tests for ``PredictionStore.delete_signal``."""

    def test_delete_signal(self, store: PredictionStore, sample_predictions: pl.DataFrame) -> None:
        """Deleting a stored signal removes its directory."""
        store.save(sample_predictions, "test_signal")
        assert "test_signal" in store.list_signals()
        assert store.delete_signal("test_signal") is True
        assert "test_signal" not in store.list_signals()

    def test_delete_nonexistent_signal(self, store: PredictionStore) -> None:
        """Deleting an absent signal reports ``False``."""
        assert store.delete_signal("nonexistent_signal") is False


def test_save_keeps_existing_history_when_parquet_write_dies(
    store: PredictionStore, sample_predictions: pl.DataFrame, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that dies midway leaves the previous predictions.parquet intact."""
    store.save(sample_predictions, "test_signal")
    path = store._get_signal_dir("test_signal") / store.PREDICTIONS_FILE

    def _torn_write(self: pl.DataFrame, file, *args, **kwargs) -> None:
        Path(file).write_bytes(b"PAR1 torn")
        raise OSError("disk went away")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _torn_write)
    later = sample_predictions.with_columns(pl.col("timestamp").dt.offset_by("3d"))
    with pytest.raises(OSError):
        store.save(later, "test_signal")

    assert pl.read_parquet(path).height == sample_predictions.height
