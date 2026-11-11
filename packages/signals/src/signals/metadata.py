"""Signal output serialization for dashboard consumption."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from .ids import validate_identifier


def validate_metrics(metrics: dict[str, float], label: str = "metrics") -> None:
    """Validate metrics dict contains numeric values."""
    if not isinstance(metrics, dict):
        raise ValueError(f"{label} must be a dict")
    for key, value in metrics.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be non-empty strings")
        if value is None or not isinstance(value, (int, float)):
            raise ValueError(f"{label}.{key} must be numeric")


def validate_data_range(data_range: dict[str, str], label: str = "data_range") -> None:
    """Validate data range dict has start/end string values."""
    if not isinstance(data_range, dict):
        raise ValueError(f"{label} must be a dict")
    for key in ("start", "end"):
        if key not in data_range:
            raise ValueError(f"{label} missing '{key}'")
        if not isinstance(data_range[key], str) or not data_range[key]:
            raise ValueError(f"{label}.{key} must be a non-empty string")


def validate_predictions_frame(df: pl.DataFrame) -> None:
    """Validate canonical prediction frame."""
    if "timestamp" not in df.columns:
        raise ValueError("Missing 'timestamp' column")
    timestamp_dtype = df["timestamp"].dtype
    if not (isinstance(timestamp_dtype, pl.Datetime) or timestamp_dtype == pl.Date):
        raise ValueError(f"'timestamp' must be date/datetime dtype, got {timestamp_dtype}")
    if "prediction" not in df.columns:
        raise ValueError("Missing 'prediction' column")
    prediction_dtype = df["prediction"].dtype
    if not prediction_dtype.is_numeric():
        raise ValueError(f"'prediction' must be numeric, got {prediction_dtype}")
    if df["prediction"].null_count() > 0:
        raise ValueError("'prediction' contains null values")


@dataclass
class SignalMetadata:
    """Rich metadata about signal training configuration and data.

    Captured by SignalRunner for dashboard display and reproducibility.
    """

    # Data characteristics
    data_start: str  # "2021-01-01"
    data_end: str  # "2025-01-02"
    n_samples: int  # Total samples in dataset
    n_features: int  # Number of features used
    feature_list: list[str]  # ["momentum_7d", "volatility_20d", ...]
    target: str  # "direction_90d" or "selected_asset"

    # Model info
    model_type: str  # "xgboost", "lightgbm", "rule_based"
    model_params: dict[str, Any]  # {"max_depth": 4, ...}

    # CV metrics (optional)
    cv_metrics: dict[str, float] | None = None  # {"accuracy": 0.55, "auc": 0.62}

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalMetadata":
        """Create from dict (e.g., from JSON)."""
        return cls(**data)

    def validate(self) -> None:
        """Validate SignalMetadata invariants."""
        if not self.data_start or not self.data_end:
            raise ValueError("SignalMetadata requires data_start and data_end")
        if self.n_samples <= 0:
            raise ValueError("SignalMetadata.n_samples must be positive")
        if self.n_features <= 0:
            raise ValueError("SignalMetadata.n_features must be positive")
        if not self.feature_list:
            raise ValueError("SignalMetadata.feature_list cannot be empty")
        if not self.target:
            raise ValueError("SignalMetadata.target cannot be empty")
        if not self.model_type:
            raise ValueError("SignalMetadata.model_type cannot be empty")


@dataclass
class SignalOutput:
    """Serializable signal predictions for dashboard consumption.

    Mirrors BacktestOutput structure for consistency. Uses run_id format
    (run-YYYYMMDD-HHMMSS) for versioning signal runs.

    Attributes:
        signal_id: Unique identifier for the signal (e.g., "example_direction").
        run_id: Run identifier (e.g., "run-20260116-140000").
        predictions: DataFrame with predictions [timestamp, prediction, ...].
        metrics: Dict of signal quality metrics (accuracy, auc, etc.).
        config: Signal configuration dict.
        created_at: Timestamp when this result was created.
        data_range: Optional dict with start/end dates.
        metadata: Optional rich metadata about training.
    """

    signal_id: str
    run_id: str
    predictions: pl.DataFrame
    metrics: dict[str, float] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    data_range: dict[str, str] | None = None
    metadata: SignalMetadata | None = None

    def save(self, db_root: Path) -> Path:
        """Save to db/signals/{signal_id}/{run_id}/.

        Creates:
            - predictions.parquet: Signal predictions
            - meta.json: Metrics, config, and metadata
            - model.pkl: Trained model (if present, saved separately by runner)

        Args:
            db_root: Root of the db/ directory.

        Returns:
            Path to the run directory.
        """
        self.validate()
        db_root = Path(db_root)
        run_dir = db_root / "signals" / self.signal_id / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save predictions as parquet
        parquet_path = run_dir / "predictions.parquet"
        self.predictions.write_parquet(
            parquet_path, compression="zstd", compression_level=3
        )

        # Save metadata as JSON
        meta = {
            "signal_id": self.signal_id,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "config": self.config,
            "data_range": self.data_range,
            "metadata": self.metadata.to_dict() if self.metadata else None,
        }
        meta_path = run_dir / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        return run_dir

    def validate(self) -> None:
        """Validate SignalOutput contract."""
        validate_identifier(self.signal_id, "signal_id")
        validate_identifier(self.run_id, "run_id")
        if not isinstance(self.config, dict):
            raise ValueError("config must be a dict")
        validate_metrics(self.metrics, label="signal metrics")
        validate_predictions_frame(self.predictions)
        if self.data_range is not None:
            validate_data_range(self.data_range)
        if self.metadata is not None:
            self.metadata.validate()

    @classmethod
    def from_path(cls, path: Path) -> "SignalOutput":
        """Load from directory containing predictions.parquet + meta.json.

        Args:
            path: Directory containing the files.

        Returns:
            SignalOutput instance.
        """
        path = Path(path)

        # Load parquet
        parquet_path = path / "predictions.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"No predictions.parquet in {path}")
        predictions = pl.read_parquet(parquet_path)

        # Load metadata
        meta_path = path / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"No meta.json in {path}")
        with open(meta_path) as f:
            meta = json.load(f)

        # Parse signal metadata if present
        signal_metadata = None
        if meta.get("metadata"):
            signal_metadata = SignalMetadata.from_dict(meta["metadata"])

        # Support both run_id (new) and version (legacy) formats
        run_id = meta.get("run_id") or meta.get("version", "unknown")

        return cls(
            signal_id=meta["signal_id"],
            run_id=run_id,
            predictions=predictions,
            metrics=meta.get("metrics", {}),
            config=meta.get("config", {}),
            created_at=datetime.fromisoformat(meta["created_at"]),
            data_range=meta.get("data_range"),
            metadata=signal_metadata,
        )
