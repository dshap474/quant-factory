"""Signals-owned append-only prediction history storage.

``PredictionStore`` persists validated signal predictions under one directory
per signal and exposes the small read/write surface used by signal runners and
strategy consumers.

Usage::

    >>> from pathlib import Path
    >>> import polars as pl
    >>> from signals import PredictionStore
    >>> store = PredictionStore(Path("db/signals"))
    >>> store.save(
    ...     pl.DataFrame({"timestamp": [], "prediction": []}),
    ...     "my_signal",
    ... )

The store owns signal-history persistence, not model inference or lifecycle.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_\\-]{0,127}$")


# --------------------------------------------------------------------------- #
# Prediction store
# --------------------------------------------------------------------------- #

class PredictionStore:
    """Store and retrieve predictions with append-only history.

    Storage layout::

        DB_ROOT/signals/{signal_name}/
            predictions.parquet      # Append-only prediction history
            latest.json              # Most recent prediction metadata
            index.json               # Signal metadata and date ranges
            runs.json                # Optional per-run metadata (by run_id)

    Predictions are stored as one parquet file per signal. This keeps date
    range queries simple while preserving append-only signal history.
    """

    PREDICTIONS_FILE = "predictions.parquet"
    LATEST_FILE = "latest.json"
    INDEX_FILE = "index.json"
    RUNS_FILE = "runs.json"

    def __init__(self, signals_dir: Path | str) -> None:
        """Initialize a store rooted at ``signals_dir``."""
        self.signals_dir = Path(signals_dir)
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------- #
    # Public persistence and query methods
    # ----------------------------------------------------------------------- #

    def save(
        self,
        predictions: pl.DataFrame,
        signal_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Append predictions for ``signal_name`` and return its parquet path.

        Existing rows are deduplicated by ``timestamp`` (or by
        ``timestamp`` + ``asset`` for cross-sectional frames), keeping the
        newest ``predicted_at`` row when available.
        """
        self._validate_predictions(predictions, signal_name)
        signal_dir = self._get_signal_dir(signal_name)
        signal_dir.mkdir(parents=True, exist_ok=True)

        predictions_path = signal_dir / self.PREDICTIONS_FILE
        if predictions_path.exists():
            combined = self._append_predictions(predictions_path, predictions)
        else:
            combined = predictions
        self._validate_timestamp_continuity(combined)

        tmp_path = predictions_path.with_name(f"{predictions_path.name}.tmp-{uuid4().hex}")
        combined.write_parquet(
            tmp_path,
            compression="zstd",
            compression_level=3,
        )
        tmp_path.replace(predictions_path)

        self._update_latest(signal_dir, predictions, metadata)
        self._update_index(signal_dir, combined)
        self._update_runs(signal_dir, predictions, metadata)

        logger.info(
            "Saved %d predictions for signal %s (total: %d)",
            len(predictions),
            signal_name,
            len(combined),
        )
        return predictions_path

    def get_history(
        self,
        signal_name: str,
        start_date: date | datetime | str | None = None,
        end_date: date | datetime | str | None = None,
    ) -> pl.DataFrame:
        """Return persisted history, optionally filtered by inclusive dates.

        Raises ``KeyError`` when no predictions have been stored for the
        signal.
        """
        signal_dir = self._get_signal_dir(signal_name)
        predictions_path = signal_dir / self.PREDICTIONS_FILE
        if not predictions_path.exists():
            raise KeyError(f"No predictions found for signal: {signal_name}")

        df = pl.read_parquet(predictions_path)
        if start_date is not None:
            df = df.filter(pl.col("timestamp") >= self._parse_date(start_date))
        if end_date is not None:
            df = df.filter(pl.col("timestamp") <= self._parse_date(end_date))
        return df.sort("timestamp")

    def get_latest(self, signal_name: str) -> dict[str, Any] | None:
        """Return the latest metadata record, or ``None`` when absent."""
        latest_path = self._get_signal_dir(signal_name) / self.LATEST_FILE
        if not latest_path.exists():
            return None
        return json.loads(latest_path.read_text())

    def list_signals(self) -> list[str]:
        """Return sorted signal names with persisted prediction files."""
        return sorted(
            path.name
            for path in self.signals_dir.iterdir()
            if path.is_dir() and (path / self.PREDICTIONS_FILE).exists()
        )

    def get_signal_info(self, signal_name: str) -> dict[str, Any] | None:
        """Return persisted index metadata for a signal, or ``None``."""
        index_path = self._get_signal_dir(signal_name) / self.INDEX_FILE
        if not index_path.exists():
            return None
        return json.loads(index_path.read_text())

    def delete_signal(self, signal_name: str) -> bool:
        """Delete all persisted history for a signal and report whether it existed."""
        import shutil

        signal_dir = self._get_signal_dir(signal_name)
        if not signal_dir.exists():
            return False
        shutil.rmtree(signal_dir)
        logger.info("Deleted predictions for signal: %s", signal_name)
        return True

    # ----------------------------------------------------------------------- #
    # Validation and append helpers
    # ----------------------------------------------------------------------- #

    def _get_signal_dir(self, signal_name: str) -> Path:
        """Return the on-disk directory for a signal."""
        return self.signals_dir / signal_name

    def _validate_predictions(self, predictions: pl.DataFrame, signal_name: str) -> None:
        """Validate the persisted prediction frame contract."""
        if not isinstance(signal_name, str) or not signal_name:
            raise ValueError("signal_name must be a non-empty string")
        if not _ID_PATTERN.match(signal_name):
            raise ValueError(
                f"signal_name must match {_ID_PATTERN.pattern}. Got: {signal_name}"
            )
        if "timestamp" not in predictions.columns:
            raise ValueError("predictions must include 'timestamp' column")
        if "prediction" not in predictions.columns:
            raise ValueError("predictions must include 'prediction' column")
        if len(predictions) == 0:
            return

        ts_dtype = predictions["timestamp"].dtype
        if not isinstance(ts_dtype, pl.Datetime) and ts_dtype != pl.Date:
            raise ValueError(f"'timestamp' must be date/datetime dtype, got {ts_dtype}")
        if not predictions["prediction"].dtype.is_numeric():
            raise ValueError(
                f"'prediction' must be numeric, got {predictions['prediction'].dtype}"
            )
        if predictions["timestamp"].null_count() > 0:
            raise ValueError("'timestamp' contains null values")
        if predictions["prediction"].null_count() > 0:
            raise ValueError("'prediction' contains null values")
        if "signal_name" in predictions.columns:
            unique_signals = predictions["signal_name"].unique().to_list()
            if len(unique_signals) > 1 or unique_signals[0] != signal_name:
                raise ValueError("predictions.signal_name must match signal_name argument")
        if "model_id" in predictions.columns:
            model_ids = predictions["model_id"].drop_nulls().unique().to_list()
            for model_id in model_ids:
                if not isinstance(model_id, str) or not model_id:
                    raise ValueError("model_id values must be non-empty strings")
                if not _ID_PATTERN.match(model_id):
                    raise ValueError(
                        f"model_id must match {_ID_PATTERN.pattern}. Got: {model_id}"
                    )

    def _append_predictions(
        self,
        existing_path: Path,
        new_predictions: pl.DataFrame,
    ) -> pl.DataFrame:
        """Append rows and deduplicate by timestamp and optional asset."""
        existing = pl.read_parquet(existing_path)
        combined = pl.concat([existing, new_predictions])
        key_cols = ["timestamp"]
        if "asset" in combined.columns:
            key_cols.append("asset")

        if "predicted_at" in combined.columns:
            combined = combined.sort(
                [*key_cols, "predicted_at"],
                descending=[False] * len(key_cols) + [True],
            )
        else:
            combined = combined.sort(key_cols)
        combined = combined.unique(subset=key_cols, keep="first")
        return combined.sort(key_cols)

    def _validate_timestamp_continuity(self, predictions: pl.DataFrame) -> None:
        """Reject duplicate logical prediction keys before writing."""
        if len(predictions) == 0:
            return

        key_cols = ["timestamp"]
        if "asset" in predictions.columns:
            key_cols.append("asset")
        sorted_df = predictions.sort(key_cols)
        has_duplicates = sorted_df.select(
            pl.struct(key_cols).is_duplicated().any().alias("has_duplicates")
        )["has_duplicates"][0]
        if has_duplicates:
            raise ValueError(f"Duplicate prediction keys found for {key_cols}")

    # ----------------------------------------------------------------------- #
    # Metadata sidecar updates
    # ----------------------------------------------------------------------- #

    def _update_latest(
        self,
        signal_dir: Path,
        predictions: pl.DataFrame,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Write metadata for the most recent row in this save."""
        latest_row = predictions.sort("timestamp", descending=True).head(1)
        if len(latest_row) == 0:
            return

        latest_data: dict[str, Any] = {
            "timestamp": str(latest_row["timestamp"][0]),
            "prediction": float(latest_row["prediction"][0]),
            "model_id": (
                str(latest_row["model_id"][0])
                if "model_id" in latest_row.columns
                else None
            ),
            "predicted_at": (
                str(latest_row["predicted_at"][0])
                if "predicted_at" in latest_row.columns
                else None
            ),
        }
        if metadata:
            latest_data["metadata"] = metadata
        (signal_dir / self.LATEST_FILE).write_text(
            json.dumps(latest_data, indent=2, default=str)
        )

    def _update_index(self, signal_dir: Path, predictions: pl.DataFrame) -> None:
        """Write aggregate signal metadata."""
        index_path = signal_dir / self.INDEX_FILE
        if len(predictions) == 0:
            index_data = {
                "date_range": {"start": None, "end": None},
                "row_count": 0,
                "model_ids": [],
                "run_ids": [],
                "run_count": 0,
                "last_updated": datetime.now().isoformat(),
            }
            index_path.write_text(json.dumps(index_data, indent=2, default=str))
            return

        timestamps = predictions["timestamp"]
        model_ids = (
            predictions["model_id"].unique().to_list()
            if "model_id" in predictions.columns
            else []
        )
        run_ids = (
            predictions["run_id"].unique().to_list()
            if "run_id" in predictions.columns
            else []
        )
        index_data = {
            "date_range": {
                "start": str(timestamps.min()),
                "end": str(timestamps.max()),
            },
            "row_count": len(predictions),
            "model_ids": model_ids,
            "run_ids": run_ids,
            "run_count": len(run_ids) if run_ids else 1,
            "last_updated": datetime.now().isoformat(),
        }
        index_path.write_text(json.dumps(index_data, indent=2, default=str))

    def _update_runs(
        self,
        signal_dir: Path,
        predictions: pl.DataFrame,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Merge per-run metadata into ``runs.json``."""
        if "run_id" in predictions.columns:
            run_ids = [str(rid) for rid in predictions["run_id"].drop_nulls().unique().to_list()]
        elif metadata and "run_id" in metadata:
            run_ids = [str(metadata["run_id"])]
        else:
            run_ids = []
        if not run_ids:
            return

        runs_path = signal_dir / self.RUNS_FILE
        runs_payload: dict[str, Any] = {
            "runs": {},
            "last_updated": datetime.now().isoformat(),
        }
        if runs_path.exists():
            try:
                runs_payload = json.loads(runs_path.read_text())
            except json.JSONDecodeError:
                pass

        runs_data = runs_payload.get("runs", {})
        default_created_at = None
        if "predicted_at" in predictions.columns:
            default_created_at = predictions["predicted_at"].max()
        if default_created_at is None and "timestamp" in predictions.columns:
            default_created_at = predictions["timestamp"].max()

        data_range = None
        if "timestamp" in predictions.columns and len(predictions) > 0:
            data_range = {
                "start": str(predictions["timestamp"].min()),
                "end": str(predictions["timestamp"].max()),
            }

        for run_id in run_ids:
            updated = dict(runs_data.get(run_id, {}))
            if metadata:
                updated.update(metadata)
            updated.setdefault("run_id", run_id)
            if data_range is not None:
                updated.setdefault("data_range", data_range)
            if default_created_at is not None:
                updated.setdefault("created_at", str(default_created_at))
            runs_data[run_id] = updated

        runs_payload["runs"] = runs_data
        runs_payload["last_updated"] = datetime.now().isoformat()
        runs_path.write_text(json.dumps(runs_payload, indent=2, default=str))

    def _parse_date(self, value: date | datetime | str) -> datetime:
        """Normalize date-like filters to a datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time())
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return datetime.strptime(value, "%Y-%m-%d")
        raise ValueError(f"Cannot parse date: {value}")


__all__ = ["PredictionStore"]
