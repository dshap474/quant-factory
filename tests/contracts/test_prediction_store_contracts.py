"""Contract tests for PredictionStore."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import polars as pl
import pytest

from signals import PredictionStore


def _predictions_df(
    *,
    signal_name: str = "test_signal",
    with_model_id: bool = False,
    with_predicted_at: bool = False,
    with_run_id: bool = False,
    offset_days: int = 0,
) -> pl.DataFrame:
    base = datetime(2024, 1, 1) + timedelta(days=offset_days)
    timestamps = [base, base + timedelta(days=1)]
    data: dict[str, list] = {
        "timestamp": timestamps,
        "prediction": [0.1, 0.2],
    }
    if with_model_id:
        data["model_id"] = ["model-1", "model-1"]
    if with_predicted_at:
        data["predicted_at"] = [
            base + timedelta(hours=1),
            base + timedelta(hours=2),
        ]
    if with_run_id:
        data["run_id"] = ["run-test-001", "run-test-001"]
    return pl.DataFrame(data).with_columns(
        pl.Series("signal_name", [signal_name, signal_name])
    )


def _empty_predictions_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": pl.Series("timestamp", [], dtype=pl.Datetime),
            "prediction": pl.Series("prediction", [], dtype=pl.Float64),
        }
    )


class TestPredictionStoreContracts:
    def test_save_roundtrip_and_list(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(with_model_id=True)
        path = store.save(preds, "test_signal", metadata={"foo": "bar"})
        store.save(preds, "test_signal")

        assert path.exists()
        assert store.list_signals() == ["test_signal"]

        latest = store.get_latest("test_signal")
        assert latest is not None
        assert latest["prediction"] == 0.2
        assert latest["model_id"] == "model-1"

        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["row_count"] == 2

        history = store.get_history("test_signal")
        assert len(history) == 2

    def test_getters_return_none_when_missing(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        assert store.get_latest("missing") is None
        assert store.get_signal_info("missing") is None
        with pytest.raises(KeyError):
            store.get_history("missing")

    def test_append_predictions_dedupes_by_timestamp(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "model_id": ["model-1", "model-1"],
                "predicted_at": [base + timedelta(hours=1), base + timedelta(hours=2)],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        store.save(preds, "test_signal")

        newer = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.9, 0.95],
                "model_id": ["model-1", "model-1"],
                "predicted_at": [base + timedelta(hours=3), base + timedelta(hours=4)],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        store.save(newer, "test_signal")

        history = store.get_history("test_signal")
        assert len(history) == 2
        assert history["prediction"].to_list() == [0.9, 0.95]

    def test_get_history_date_filters(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        store.save(_predictions_df(), "test_signal")

        history = store.get_history("test_signal", start_date="2024-01-02")
        assert len(history) == 1

    def test_delete_signal(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        store.save(_predictions_df(), "test_signal")
        assert store.delete_signal("test_signal") is True
        assert store.delete_signal("missing") is False

    def test_parse_date_variants(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        assert store._parse_date(date(2024, 1, 1)).date() == date(2024, 1, 1)
        dt = datetime(2024, 1, 3, 12, 0, 0)
        assert store._parse_date(dt) == dt
        assert store._parse_date("2024-01-02").date() == date(2024, 1, 2)
        with pytest.raises(ValueError, match="Cannot parse date"):
            store._parse_date(123)  # type: ignore[arg-type]

    def test_validation_rejects_bad_signal_name(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        with pytest.raises(ValueError, match="signal_name"):
            store.save(_predictions_df(), "BadID")

    def test_validation_rejects_missing_timestamp(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame({"prediction": [0.1]})
        with pytest.raises(ValueError, match="timestamp"):
            store.save(preds, "test_signal")

    def test_validation_rejects_non_numeric_prediction(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame(
            {"timestamp": [datetime(2024, 1, 1)], "prediction": ["bad"]}
        )
        with pytest.raises(ValueError, match="prediction"):
            store.save(preds, "test_signal")

    def test_validation_rejects_nulls(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame(
            {"timestamp": [datetime(2024, 1, 1), None], "prediction": [0.1, 0.2]}
        )
        with pytest.raises(ValueError, match="null"):
            store.save(preds, "test_signal")

    def test_validation_rejects_signal_name_mismatch(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(signal_name="other_signal")
        with pytest.raises(ValueError, match="signal_name"):
            store.save(preds, "test_signal")

    def test_validation_rejects_bad_model_id(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(with_model_id=True).with_columns(
            pl.Series("model_id", ["BadID", "BadID"])
        )
        with pytest.raises(ValueError, match="model_id"):
            store.save(preds, "test_signal")

    def test_init_creates_nested_directory(self, tmp_path):
        target = tmp_path / "nested" / "signals"
        PredictionStore(target)
        assert target.exists()

    def test_init_is_idempotent_for_existing_directory(self, tmp_path):
        target = tmp_path / "signals"
        target.mkdir(parents=True, exist_ok=True)
        PredictionStore(target)
        PredictionStore(target)

    def test_save_records_run_metadata(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(with_model_id=True, with_predicted_at=True, with_run_id=True)
        store.save(
            preds,
            "test_signal",
            metadata={"run_id": "run-test-001", "metrics": {"accuracy": 0.55}},
        )

        runs_path = tmp_path / "signals" / "test_signal" / "runs.json"
        assert runs_path.exists()
        payload = json.loads(runs_path.read_text())
        assert payload["runs"]["run-test-001"]["metrics"]["accuracy"] == 0.55

    def test_latest_includes_metadata_and_predicted_at(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "model_id": ["model-1", "model-1"],
                "predicted_at": [
                    base + timedelta(hours=1),
                    base + timedelta(days=1, hours=1),
                ],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        metadata = {"run_id": "run-latest", "metrics": {"sharpe": 1.25}}
        store.save(preds, "test_signal", metadata=metadata)

        latest = store.get_latest("test_signal")
        assert latest is not None
        assert latest["timestamp"] == str(base + timedelta(days=1))
        assert latest["prediction"] == 0.2
        assert latest["model_id"] == "model-1"
        assert latest["predicted_at"] == str(base + timedelta(days=1, hours=1))
        assert latest["metadata"] == metadata

    def test_index_includes_runs_and_models(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "model_id": ["model-1", "model-2"],
                "run_id": ["run-1", "run-2"],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        store.save(preds, "test_signal")
        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["row_count"] == 2
        assert info["date_range"]["start"] == str(base)
        assert info["date_range"]["end"] == str(base + timedelta(days=1))
        assert set(info["model_ids"]) == {"model-1", "model-2"}
        assert set(info["run_ids"]) == {"run-1", "run-2"}
        assert info["run_count"] == 2
        assert "last_updated" in info

    def test_index_without_run_id_sets_run_count_one(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        store.save(_predictions_df(with_model_id=True), "test_signal")
        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["run_ids"] == []
        assert info["run_count"] == 1

    def test_index_single_row(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base],
                "prediction": [0.1],
                "signal_name": ["test_signal"],
            }
        )
        store.save(preds, "test_signal")
        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["row_count"] == 1
        assert info["date_range"]["start"] == str(base)
        assert info["date_range"]["end"] == str(base)

    def test_index_empty_predictions(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        store.save(_empty_predictions_df(), "test_signal")
        info = store.get_signal_info("test_signal")
        assert info is not None
        assert info["row_count"] == 0
        assert info["date_range"]["start"] is None
        assert info["date_range"]["end"] is None
        assert info["run_count"] == 0

    def test_runs_metadata_from_predictions_only(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "run_id": ["run-only", "run-only"],
                "predicted_at": [
                    base + timedelta(hours=1),
                    base + timedelta(days=1, hours=2),
                ],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        metadata = {"metrics": {"accuracy": 0.9}, "config": {"window": 5}}
        store.save(preds, "test_signal", metadata=metadata)

        runs_path = tmp_path / "signals" / "test_signal" / "runs.json"
        payload = json.loads(runs_path.read_text())
        run = payload["runs"]["run-only"]
        assert run["run_id"] == "run-only"
        assert run["metrics"] == {"accuracy": 0.9}
        assert run["config"] == {"window": 5}
        assert run["created_at"] == str(base + timedelta(days=1, hours=2))
        assert run["data_range"] == {
            "start": str(base),
            "end": str(base + timedelta(days=1)),
        }
        assert "last_updated" in payload

    def test_runs_metadata_from_metadata_only(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(with_predicted_at=True)
        store.save(preds, "test_signal", metadata={"run_id": "run-meta"})

        runs_path = tmp_path / "signals" / "test_signal" / "runs.json"
        payload = json.loads(runs_path.read_text())
        assert "run-meta" in payload["runs"]

    def test_runs_metadata_falls_back_to_timestamp(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "run_id": ["run-fallback", "run-fallback"],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        store.save(preds, "test_signal")

        runs_path = tmp_path / "signals" / "test_signal" / "runs.json"
        payload = json.loads(runs_path.read_text())
        run = payload["runs"]["run-fallback"]
        assert run["created_at"] == str(base + timedelta(days=1))

    def test_runs_metadata_preserves_created_at(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "run_id": ["run-meta", "run-meta"],
                "predicted_at": [
                    base + timedelta(hours=1),
                    base + timedelta(days=1, hours=1),
                ],
                "signal_name": ["test_signal", "test_signal"],
            }
        )
        metadata = {"run_id": "run-meta", "created_at": "2024-01-01T12:00:00"}
        store.save(preds, "test_signal", metadata=metadata)

        runs_path = tmp_path / "signals" / "test_signal" / "runs.json"
        payload = json.loads(runs_path.read_text())
        assert payload["runs"]["run-meta"]["created_at"] == "2024-01-01T12:00:00"

    def test_get_history_end_date_inclusive(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        store.save(_predictions_df(), "test_signal")
        history = store.get_history("test_signal", end_date="2024-01-01")
        assert len(history) == 1
        assert history["timestamp"][0] == datetime(2024, 1, 1)

    def test_list_signals_excludes_empty_dirs(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        (tmp_path / "signals" / "empty_signal").mkdir(parents=True, exist_ok=True)
        store.save(_predictions_df(), "test_signal")
        assert store.list_signals() == ["test_signal"]

    def test_validation_rejects_empty_signal_name(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        with pytest.raises(ValueError, match="signal_name"):
            store.save(_predictions_df(), "")

    def test_validation_rejects_non_string_signal_name(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        with pytest.raises(ValueError, match="signal_name"):
            store.save(_predictions_df(), 123)  # type: ignore[arg-type]

    def test_validation_rejects_missing_prediction_column(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)]})
        with pytest.raises(ValueError, match="prediction"):
            store.save(preds, "test_signal")

    def test_validation_rejects_prediction_nulls(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame(
            {"timestamp": [datetime(2024, 1, 1)], "prediction": [None]}
        )
        with pytest.raises(ValueError, match="prediction"):
            store.save(preds, "test_signal")

    def test_validation_accepts_date_dtype(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = pl.DataFrame(
            {
                "timestamp": [date(2024, 1, 1), date(2024, 1, 2)],
                "prediction": [0.1, 0.2],
            }
        )
        store.save(preds, "test_signal")

    def test_validation_rejects_multiple_signal_names(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        base = datetime(2024, 1, 1)
        preds = pl.DataFrame(
            {
                "timestamp": [base, base + timedelta(days=1)],
                "prediction": [0.1, 0.2],
                "signal_name": ["test_signal", "other_signal"],
            }
        )
        with pytest.raises(ValueError, match="signal_name"):
            store.save(preds, "test_signal")

    def test_validation_rejects_empty_model_id(self, tmp_path):
        store = PredictionStore(tmp_path / "signals")
        preds = _predictions_df(with_model_id=True).with_columns(
            pl.Series("model_id", ["", ""])
        )
        with pytest.raises(ValueError, match="model_id"):
            store.save(preds, "test_signal")
