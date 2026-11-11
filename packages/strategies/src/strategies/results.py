"""Backtest output serialization: ``backtest.parquet`` + ``meta.json`` in one run directory.

USAGE:
    BacktestOutput(strategy_id="p", run_id=run_id, equity=frame, metrics={}).save(run_dir)
    output = BacktestOutput.from_path(run_dir)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from .contracts import (
    validate_backtest_equity,
    validate_data_range,
    validate_identifier,
    validate_metrics,
)


@dataclass
class TrainingMetadata:
    """Metadata about training configuration and data split."""

    data_start: str
    data_end: str
    resolution_minutes: int
    n_assets: int
    asset_list: list[str]
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_rows: int
    test_rows: int
    features: list[str]
    target: str
    model_type: str
    model_params: dict[str, Any]
    portfolio_method: str = "long_short"
    top_k: int = 5
    bottom_k: int = 5

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainingMetadata":
        """Create from dict."""
        return cls(**data)

    def validate(self) -> None:
        """Validate TrainingMetadata invariants."""
        if not self.data_start or not self.data_end:
            raise ValueError("TrainingMetadata requires data_start and data_end")
        if self.resolution_minutes <= 0:
            raise ValueError("TrainingMetadata.resolution_minutes must be positive")
        if self.n_assets <= 0:
            raise ValueError("TrainingMetadata.n_assets must be positive")
        if not self.asset_list:
            raise ValueError("TrainingMetadata.asset_list cannot be empty")
        if self.train_rows < 0 or self.test_rows < 0:
            raise ValueError("TrainingMetadata rows must be non-negative")
        if not self.features:
            raise ValueError("TrainingMetadata.features cannot be empty")
        if not self.target:
            raise ValueError("TrainingMetadata.target cannot be empty")
        if not self.model_type:
            raise ValueError("TrainingMetadata.model_type cannot be empty")


@dataclass
class BacktestOutput:
    """Serializable backtest result for dashboard consumption."""

    strategy_id: str
    run_id: str
    equity: pl.DataFrame
    metrics: dict[str, float]
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    data_range: dict[str, str] | None = None
    training_metadata: TrainingMetadata | None = None
    strategy_type: str | None = None
    memory_version: str | None = None
    preset: str | None = None

    def meta(self) -> dict[str, Any]:
        """Return the ``meta.json`` payload."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_type": self.strategy_type,
            "memory_version": self.memory_version,
            "preset": self.preset,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "config": self.config,
            "data_range": self.data_range,
            "training_metadata": self.training_metadata.to_dict() if self.training_metadata else None,
        }

    def save(self, run_dir: Path) -> Path:
        """Write ``backtest.parquet`` and ``meta.json`` into ``run_dir``."""
        self.validate()
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        self.equity.write_parquet(run_dir / "backtest.parquet", compression="zstd", compression_level=3)
        (run_dir / "meta.json").write_text(json.dumps(self.meta(), indent=2, default=str))
        return run_dir

    def validate(self) -> None:
        """Validate BacktestOutput contract."""
        validate_identifier(self.strategy_id, "strategy_id")
        validate_identifier(self.run_id, "run_id")
        if not isinstance(self.config, dict):
            raise ValueError("config must be a dict")
        validate_metrics(self.metrics, label="backtest metrics")
        validate_backtest_equity(self.equity)
        if self.data_range is not None:
            validate_data_range(self.data_range)
        if self.training_metadata is not None:
            self.training_metadata.validate()

    @classmethod
    def from_path(cls, path: Path) -> "BacktestOutput":
        """Load from a directory containing ``backtest.parquet`` + ``meta.json``."""
        path = Path(path)
        for name in ("backtest.parquet", "meta.json"):
            if not (path / name).exists():
                raise FileNotFoundError(f"No {name} in {path}")
        meta = json.loads((path / "meta.json").read_text())
        training = meta.get("training_metadata")
        return cls(
            strategy_id=meta["strategy_id"],
            run_id=meta["run_id"],
            equity=pl.read_parquet(path / "backtest.parquet"),
            metrics=meta.get("metrics", {}),
            config=meta.get("config", {}),
            created_at=datetime.fromisoformat(meta["created_at"]),
            data_range=meta.get("data_range"),
            training_metadata=TrainingMetadata.from_dict(training) if training else None,
            strategy_type=meta.get("strategy_type"),
            memory_version=meta.get("memory_version"),
            preset=meta.get("preset"),
        )
