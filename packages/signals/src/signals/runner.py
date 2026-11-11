"""Signal runner base class with auto-persistence.

This module provides the SignalRunner abstract base class that all
signals should inherit from. It handles:
- Running the signal computation pipeline (load -> compute -> persist)
- Automatically saving results to DB_ROOT/signals/ via PredictionStore
- Enforcing canonical prediction contracts

Subclasses must implement:
- load_data(): Load input data
- compute(): Produce predictions DataFrame [timestamp, prediction, ...]
- get_config_dict(): Return config for serialization

Optionally:
- get_metadata(): Return rich SignalMetadata for dashboard
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from config import QUANT_DB_ROOT

from signals.contracts import validate_predictions_frame

from .ids import generate_run_id, validate_identifier

if TYPE_CHECKING:
    from .metadata import SignalMetadata


# Default DB root (canonical)
DEFAULT_DB_ROOT = QUANT_DB_ROOT


@dataclass
class SignalRunConfig:
    """Configuration for a signal run.

    Attributes:
        signal_id: Unique identifier for this signal (e.g., "btc-trend-90d").
            Used as the directory name in DB_ROOT/signals/.
        signal_type: Type of signal (e.g., "example").
            Used for grouping in the signal registry and persisted outputs.
        save: Whether to automatically save results to DB_ROOT/signals/.
        db_root: Root directory for persistence. Default is quant-factory/db/.
    """

    signal_id: str
    signal_type: str = "unknown"
    save: bool = True
    db_root: Path = field(default_factory=lambda: DEFAULT_DB_ROOT)

    def __post_init__(self) -> None:
        """Validate identifiers and normalize paths."""
        if isinstance(self.db_root, str):
            self.db_root = Path(self.db_root)
        validate_identifier(self.signal_id, "signal_id")
        if self.signal_type:
            validate_identifier(self.signal_type, "signal_type")


@dataclass
class SignalRunResult:
    """Result from running a signal.

    Attributes:
        predictions: DataFrame with predictions [timestamp, prediction, ...].
        metrics: Performance metrics dict (optional).
        config: Signal configuration dict (for reproducibility).
        run_id: Unique run identifier (set if saved).
        run_dir: Path to saved signal directory (set if saved).
    """

    predictions: pl.DataFrame
    metrics: dict[str, float]
    config: dict[str, Any]
    run_id: str | None = None
    run_dir: Path | None = None

    def summary(self) -> str:
        """Return human-readable summary."""
        lines = [
            f"SignalRunResult(run_id={self.run_id})",
            "=" * 50,
            f"Predictions: {len(self.predictions)} rows",
        ]
        if self.metrics:
            lines.append("Metrics:")
            for key, value in self.metrics.items():
                if isinstance(value, float):
                    lines.append(f"  {key}: {value:.4f}")
                else:
                    lines.append(f"  {key}: {value}")
        if self.run_dir:
            lines.append(f"Saved to: {self.run_dir}")
        return "\n".join(lines)


class SignalRunner(ABC):
    """Abstract base class for signal runners.

    SignalRunner orchestrates the full signal lifecycle:
    1. Load data via load_data()
    2. Compute signal via compute()
    3. Save results to DB_ROOT/signals/ via PredictionStore (append-only)

    Subclasses must implement:
        - load_data(): Load input data
        - compute(data): Produce predictions DataFrame
        - get_config_dict(): Return config as serializable dict

    Optionally implement:
        - get_metadata(): Return SignalMetadata for dashboard

    The base class handles:
        - Result persistence to DB_ROOT/signals/{signal_id}/ (append-only)
        - Run ID generation
        - Prediction validation

    Example:
        >>> class MySignalRunner(SignalRunner):
        ...     def __init__(self, param: int = 10, save: bool = True):
        ...         super().__init__(SignalRunConfig(
        ...             signal_id="my_signal",
        ...             signal_type="my-signal-type",
        ...             save=save,
        ...         ))
        ...         self.param = param
        ...
        ...     def load_data(self) -> pl.DataFrame:
        ...         return load_my_data()
        ...
        ...     def compute(self, data: pl.DataFrame) -> pl.DataFrame:
        ...         # Signal logic here (rule-based, ML, composite, etc.)
        ...         return pl.DataFrame({"timestamp": [...], "prediction": [...]})
        ...
        ...     def get_config_dict(self) -> dict[str, Any]:
        ...         return {"param": self.param}
        ...
        >>> runner = MySignalRunner(param=20)
        >>> result = runner.run()
        >>> print(result.metrics)
    """

    def __init__(self, run_config: SignalRunConfig) -> None:
        """Initialize runner with configuration.

        Args:
            run_config: Signal run configuration.
        """
        self.run_config = run_config

    @abstractmethod
    def load_data(self) -> pl.DataFrame:
        """Load input data for signal computation.

        Returns:
            DataFrame with input data. Must include a timestamp column.
        """
        pass

    @abstractmethod
    def compute(self, data: pl.DataFrame) -> pl.DataFrame:
        """Compute the signal.

        This is where signal logic lives — ML model, rule-based indicator,
        composite score, regime detector, etc. The implementation is entirely
        up to the subclass.

        Args:
            data: DataFrame from load_data().

        Returns:
            DataFrame with predictions. Must include:
            - timestamp: Datetime column
            - prediction: Signal value (float)
            Optional columns: asset, model_id, predicted_at, run_id, signal_name
        """
        pass

    @abstractmethod
    def get_config_dict(self) -> dict[str, Any]:
        """Return signal config as serializable dict.

        Used for saving run metadata for reproducibility.

        Returns:
            Dict of configuration parameters.
        """
        pass

    def get_metadata(self) -> "SignalMetadata | None":
        """Return signal metadata for this run.

        Override in subclasses to provide rich metadata including:
        - Data characteristics (date range, samples, features)
        - Model type and parameters
        - CV metrics

        Base implementation returns None (metadata is optional).

        Returns:
            SignalMetadata with training configuration, or None.
        """
        return None

    def run(self) -> SignalRunResult:
        """Execute signal: load_data -> compute -> persist.

        Returns:
            SignalRunResult with predictions, metrics, and paths.
        """
        # 1. Load data
        print(f"Loading data for {self.run_config.signal_id}...")
        data = self.load_data()
        print(f"  Loaded {len(data)} rows")

        # 2. Compute signal
        print("Computing signal...")
        predictions = self.compute(data)
        print(f"  Generated {len(predictions)} predictions")

        # 3. Validate predictions
        self._validate_predictions(predictions)

        # 4. Save if requested
        run_id, run_dir = None, None
        if self.run_config.save:
            run_id, run_dir = self._save_results(predictions)
            print(f"Saved to {run_dir}")

        # 5. Build result
        result = SignalRunResult(
            predictions=predictions,
            metrics={},
            config=self.get_config_dict(),
            run_id=run_id,
            run_dir=run_dir,
        )
        print("\n" + result.summary())

        return result

    def _validate_predictions(self, predictions: pl.DataFrame) -> None:
        """Validate that predictions conform to the signal contract."""
        validate_predictions_frame(predictions, signal_name=self.run_config.signal_id)

    def _save_results(
        self,
        predictions: pl.DataFrame,
    ) -> tuple[str, Path]:
        """Save results to DB_ROOT/signals/{signal_id}/ (append-only).

        Args:
            predictions: Predictions DataFrame.

        Returns:
            Tuple of (run_id, run_dir).
        """
        from signals.prediction_store import PredictionStore

        run_id = generate_run_id()
        created_at = datetime.now()

        # Add standard columns if missing
        if "signal_name" not in predictions.columns:
            predictions = predictions.with_columns(
                pl.lit(self.run_config.signal_id).alias("signal_name")
            )
        if "run_id" not in predictions.columns:
            predictions = predictions.with_columns(pl.lit(run_id).alias("run_id"))
        if "predicted_at" not in predictions.columns:
            predictions = predictions.with_columns(
                pl.lit(created_at).alias("predicted_at")
            )

        validate_predictions_frame(predictions, signal_name=self.run_config.signal_id)

        # Get data range
        data_range = None
        if "timestamp" in predictions.columns and len(predictions) > 0:
            ts = predictions["timestamp"]
            data_range = {
                "start": str(ts.min()),
                "end": str(ts.max()),
            }

        store = PredictionStore(self.run_config.db_root / "signals")
        store.save(
            predictions=predictions,
            signal_name=self.run_config.signal_id,
            metadata={
                "run_id": run_id,
                "created_at": created_at.isoformat(),
                "config": self.get_config_dict(),
                "data_range": data_range,
                "metadata": self.get_metadata().to_dict() if self.get_metadata() else None,
            },
        )
        run_dir = self.run_config.db_root / "signals" / self.run_config.signal_id

        return run_id, run_dir

    @classmethod
    def from_preset(
        cls,
        name: str,
        save: bool = True,
        db_root: Path | None = None,
    ) -> "SignalRunner":
        """Create runner from a named preset.

        Subclasses should override this method to load their specific
        preset format.

        Args:
            name: Preset name (without .yaml extension).
            save: Whether to persist results.
            db_root: Override DB root path.

        Returns:
            Configured SignalRunner instance.
        """
        raise NotImplementedError(
            f"{cls.__name__} must implement from_preset() to support preset loading"
        )
