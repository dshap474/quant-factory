"""Strategy runner base class: decisions, backtest, and one saved run layout.

Every strategy subclasses StrategyRunner and emits StrategyWeights. A runner either
generates its full decision history at once (``generate_weights``) or decides from
actual holdings (``_decide_with_account_state``), in which case ``run()`` drives the
shared intent ledger over ``ledger_inputs()``. Event-driven runners whose fills can't be
expressed as NAV weights override ``run_nav()`` instead and return their own daily NAV from
family-owned execution and accounting. Saved runs write one directory:
``decisions.parquet`` (StrategyWeights.save), ``backtest.parquet`` and ``meta.json``, plus
``status.json`` (state, host/pid, phase timings, engine, error) written when the run starts
and rewritten when it succeeds or fails.

USAGE:
    runner = MyRunner(StrategyRunConfig(strategy_id="my-preset", strategy_type="my-family",
                                        memory_version="v001"))
    result = runner.run()                      # saves under db/research/strategies/...
    latest = runner.decide()                   # latest decision, no backtest or save
    runner.run(decisions_path=cell / "decisions.parquet")   # caller-owned research dir
    nav = runner.run_nav()                     # event-driven runners only: [timestamp, nav]
"""

from __future__ import annotations

import json
import math
import os
import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import polars as pl
from config import QUANT_DB_ROOT

from .contracts import validate_identifier, validate_memory_version, validate_strategy_weights_contract
from .ids import generate_run_id
from .registry import StrategyRegistry
from .results import BacktestOutput, TrainingMetadata
from .weights import StrategyWeights

if TYPE_CHECKING:
    from backtest import BacktestConfig, BacktestResult

DEFAULT_DB_ROOT = QUANT_DB_ROOT
_STATUS_ERROR_CHARS = 2000


# --------------------------------------------------------------------------- #
# Run inputs and results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AccountState:
    """Account feedback at a decision timestamp; quantities are signed units.

    Usage: ``runner.decide(AccountState(timestamp=t, quantities={'BTC': 1.0},
    nav=100.0, weights={'BTC': 0.5}, cash=50.0))``.
    """

    timestamp: datetime
    quantities: Mapping[str, float]
    nav: float
    weights: Mapping[str, float]
    cash: float

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise ValueError("AccountState.timestamp must be datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("AccountState.timestamp must be timezone-aware UTC")
        if not math.isfinite(self.nav) or self.nav <= 0:
            raise ValueError("AccountState.nav must be finite and positive")
        if not math.isfinite(self.cash):
            raise ValueError("AccountState.cash must be finite")
        for name in ("quantities", "weights"):
            values = dict(getattr(self, name))
            if any(not isinstance(asset, str) or not asset.strip() for asset in values):
                raise ValueError(f"AccountState.{name} keys must be non-empty asset strings")
            if any(not math.isfinite(value) for value in values.values()):
                raise ValueError(f"AccountState.{name} values must be finite")
            object.__setattr__(self, name, MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class LedgerInputs:
    """Event grid an account-aware runner is simulated on by ``run_intent_ledger``."""

    market: pl.DataFrame
    decision_times: Sequence[datetime]
    funding_rates: pl.DataFrame | None = None
    forced_exits: Mapping[datetime, Sequence[str]] | None = None
    relisted_at: Mapping[datetime, Sequence[str]] | None = None


@dataclass
class StrategyRunConfig:
    """Configuration for a strategy run.

    Attributes:
        strategy_id: Identity stamped on every decision (usually the preset name).
        preset_name: Experiment folder for saved runs; defaults to ``strategy_id``.
        strategy_type: Registered family id.
        save: Save each ``run()`` under ``run_dir()``.
        db_root: Database root. Default is quant-factory/db/.
        backtest_config: Backtest engine configuration; the engine default when None.
        memory_version: Strategy memory version (``vNNN``); required to save.
    """

    strategy_id: str
    preset_name: str | None = None
    strategy_type: str = "unknown"
    save: bool = True
    db_root: Path = field(default_factory=lambda: DEFAULT_DB_ROOT)
    backtest_config: "BacktestConfig | None" = None
    memory_version: str | None = None

    def __post_init__(self) -> None:
        """Validate identifiers and normalize paths."""
        if isinstance(self.db_root, str):
            self.db_root = Path(self.db_root)
        validate_identifier(self.strategy_id, "strategy_id")
        if self.preset_name is not None:
            validate_identifier(self.preset_name, "preset_name")
        if self.strategy_type:
            validate_identifier(self.strategy_type, "strategy_type")
        if self.memory_version is not None:
            validate_memory_version(self.memory_version)


@dataclass
class StrategyRunResult:
    """Result from running a strategy.

    Attributes:
        weights: Decision-time weights produced by the strategy.
        effective_weights: Effective weights after shared timing materialization.
        backtest: BacktestResult from the backtest engine.
        metrics: Performance metrics dict.
        config: Strategy configuration dict (for reproducibility).
        run_id: Run identifier (set when saved under ``run_dir()``).
        run_dir: Directory holding the saved decisions (set when saved).
    """

    weights: StrategyWeights
    backtest: "BacktestResult"
    metrics: dict[str, float]
    config: dict[str, Any]
    effective_weights: StrategyWeights | None = None
    run_id: str | None = None
    run_dir: Path | None = None

    def __post_init__(self) -> None:
        """Preserve the legacy single-weights construction contract."""
        if self.effective_weights is None:
            self.effective_weights = self.weights

    def summary(self) -> str:
        """Return human-readable summary."""
        lines = [
            f"StrategyRunResult(run_id={self.run_id})",
            "=" * 50,
            self.backtest.summary(),
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Runner base class
# --------------------------------------------------------------------------- #


class StrategyRunner(ABC):
    """Base class every strategy family registers.

    Subclasses implement ``load_data`` and ``get_config_dict`` plus one decision
    method: ``generate_weights(data)`` for a full weight history, or
    ``_decide_with_account_state(data, state)`` together with ``ledger_inputs()``
    for strategies whose decisions depend on actual holdings. Event-driven families
    whose fills can't be expressed as NAV weights override ``run_nav()`` instead.
    ``write_artifacts`` adds family evidence to a saved run directory.
    """

    def __init__(self, run_config: StrategyRunConfig) -> None:
        self.run_config = run_config
        self.last_intent_result = None

    @abstractmethod
    def load_data(self) -> pl.DataFrame:
        """Return price data, wide ``[timestamp, BTC, ...]`` or panel ``[timestamp, asset, close]``."""

    @abstractmethod
    def get_config_dict(self) -> dict[str, Any]:
        """Return the serializable configuration recorded with each saved run."""

    def generate_weights(self, data: pl.DataFrame) -> StrategyWeights:
        """Return the full decision history ``[timestamp, ASSET..., CASH]``."""
        raise NotImplementedError(f"{type(self).__name__} decides from AccountState; use decide(state)")

    def _decide_with_account_state(self, data: pl.DataFrame, account_state: AccountState) -> StrategyWeights:
        """Override for strategies that consume account feedback."""
        raise NotImplementedError(f"{type(self).__name__} does not support account_state decisions")

    def ledger_inputs(self, market: Any = None) -> LedgerInputs:
        """Return the event grid for an account-aware run; ``market`` is a caller-prepared grid."""
        raise NotImplementedError(f"{type(self).__name__} must define ledger_inputs() to run account-aware")

    def get_training_metadata(self) -> TrainingMetadata | None:
        """Return training metadata recorded in ``meta.json``, when the family has any."""
        return None

    def write_artifacts(self, run_dir: Path) -> None:
        """Write family-specific evidence beside a run saved under ``run_dir()``."""

    def run_nav(self) -> pl.DataFrame:
        """Override for event-driven runners: ``[timestamp, nav]`` from the family's own execution and accounting."""
        raise NotImplementedError(f"{type(self).__name__} is not event-driven; use run()")

    @property
    def account_aware(self) -> bool:
        return type(self)._decide_with_account_state is not StrategyRunner._decide_with_account_state

    @property
    def event_driven(self) -> bool:
        return type(self).run_nav is not StrategyRunner.run_nav

    def decide(self, account_state: AccountState | None = None) -> StrategyWeights:
        """Produce and validate decision-time weights without backtest or persistence."""
        data = self.load_data()
        if account_state is None:
            return self.decide_history(data)
        weights = self._with_identity(self._decide_with_account_state(data, account_state))
        validate_strategy_weights_contract(weights, output_type=self._get_output_type())
        return weights

    def decide_history(self, data: pl.DataFrame) -> StrategyWeights:
        """Validated full decision history from already-loaded ``data`` (weight-history runners)."""
        weights = self._with_identity(self.generate_weights(data))
        validate_strategy_weights_contract(weights, output_type=self._get_output_type())
        return weights

    def _with_identity(self, weights: StrategyWeights) -> StrategyWeights:
        """Stamp this runner's strategy_id and memory version onto its output."""
        identity = {"strategy_id": self.run_config.strategy_id, "version": self.run_config.memory_version}
        for name, value in identity.items():
            current = getattr(weights, name)
            if current is not None and current != value:
                raise ValueError(f"weights.{name}={current!r} conflicts with runner {value!r}")
        return replace(weights, **identity)

    # ----------------------------------------------------------------------- #
    # Run and persistence
    # ----------------------------------------------------------------------- #

    def run(self, *, decisions_path: str | Path | None = None, market: Any = None) -> StrategyRunResult:
        """Decide over the full history, backtest, and persist the decisions.

        ``decisions_path`` saves only the decision history into a caller-owned
        research directory; otherwise ``save=True`` writes a complete run under
        ``run_dir()``, whose ``status.json`` reports the run while it executes.
        ``market`` is forwarded to ``ledger_inputs`` for account-aware runners.
        """
        if self.event_driven:
            raise TypeError(f"{type(self).__name__} is event-driven; its NAV comes from run_nav()")
        if market is not None and not self.account_aware:
            raise ValueError("market applies only to account-aware runners")

        run_id, run_dir = None, None
        if decisions_path is None and self.run_config.save:
            run_id = generate_run_id()
            run_dir = self.run_dir(run_id)
            run_dir.mkdir(parents=True, exist_ok=False)
        status = _RunStatus(run_dir, self.run_config, run_id)
        try:
            if self.account_aware:
                with status.phase("backtest"):
                    ledger = self._run_ledger(market)
                weights = effective_weights = ledger.decisions
                backtest_result = ledger.backtest
            else:
                with status.phase("load_data"):
                    data = self.load_data()
                with status.phase("decide"):
                    weights = self.decide_history(data)
                    effective_weights = self._materialize_effective_weights(weights, data)
                with status.phase("backtest"):
                    backtest_result = self._run_backtest(effective_weights, data)

            if decisions_path is not None:
                weights.save(decisions_path)
                run_dir = Path(decisions_path).parent
            elif run_id is not None:
                with status.phase("save"):
                    self._save_run(run_id, weights, effective_weights, backtest_result)
        except BaseException as exc:
            status.finish("failed", error=f"{type(exc).__name__}: {exc}"[:_STATUS_ERROR_CHARS])
            raise
        if run_id is not None:
            status.finish(
                "succeeded",
                engine=backtest_result.engine_used,
                rows=len(backtest_result.equity),
                assets=len(weights.assets),
                lag_bars=weights.execution.derive_lag_bars(),
            )

        return StrategyRunResult(
            weights=weights,
            effective_weights=effective_weights,
            backtest=backtest_result,
            metrics=dict(backtest_result.metrics),
            config=self.get_config_dict(),
            run_id=run_id,
            run_dir=run_dir,
        )

    def run_dir(self, run_id: str) -> Path:
        """Research run directory: ``research/strategies/<family>/<version>/<preset>/<run_id>``."""
        cfg = self.run_config
        if cfg.memory_version is None:
            raise ValueError("memory_version is required to save a strategy run")
        experiment = cfg.preset_name or cfg.strategy_id
        return cfg.db_root / "research" / "strategies" / cfg.strategy_type / cfg.memory_version / experiment / run_id

    def _save_run(
        self,
        run_id: str,
        weights: StrategyWeights,
        effective_weights: StrategyWeights,
        result: "BacktestResult",
    ) -> Path:
        run_dir = self.run_dir(run_id)  # created by run(), which writes status.json there first
        run_dir.mkdir(parents=True, exist_ok=True)
        weights.save(run_dir / "decisions.parquet")
        self._build_backtest_output(effective_weights, result, run_id).save(run_dir)
        self.write_artifacts(run_dir)
        return run_dir

    def _run_ledger(self, market: Any):
        """Simulate an account-aware runner, one decision per ``decision_times`` entry."""
        from backtest import BacktestConfig, run_intent_ledger

        def decide(at: datetime, state: AccountState) -> StrategyWeights:
            if getattr(self.decide, "__func__", None) is not StrategyRunner.decide:
                return self.decide(state)
            # decide(state) minus its plain validate(): the ledger validates every returned decision itself.
            weights = self._with_identity(self._decide_with_account_state(self.load_data(), state))
            output_type = self._get_output_type()
            if output_type == "market_neutral":
                validate_strategy_weights_contract(weights, output_type=output_type)
            return weights

        inputs = self.ledger_inputs(market)
        self.last_intent_result = run_intent_ledger(
            market=inputs.market,
            funding_rates=inputs.funding_rates,
            decision_times=inputs.decision_times,
            decide=decide,
            forced_exits=inputs.forced_exits,
            relisted_at=inputs.relisted_at,
            config=self.run_config.backtest_config or BacktestConfig(engine="ledger", metrics=[]),
        )
        return self.last_intent_result

    def _get_output_type(self) -> str | None:
        """Resolve output_type from registry metadata when available."""
        strategy_type = self.run_config.strategy_type
        if not strategy_type:
            return None
        try:
            metadata = StrategyRegistry.get_metadata(strategy_type)
        except KeyError:
            return None
        output_type = metadata.get("output_type")
        return str(output_type) if output_type else None

    def _run_backtest(self, weights: StrategyWeights, data: pl.DataFrame) -> "BacktestResult":
        """Backtest already-materialized weights on the unified engine."""
        from backtest import BacktestConfig, run_backtest_from_strategy_weights

        return run_backtest_from_strategy_weights(
            weights=weights,
            data=data,
            config=self.run_config.backtest_config or BacktestConfig(),
            materialize_timing=False,
        )

    def _materialize_effective_weights(self, weights: StrategyWeights, data: pl.DataFrame) -> StrategyWeights:
        """Convert decision-time weights into the effective backtest schedule."""
        from backtest import materialize_effective_weights

        prices = self._data_to_prices(data, weights.assets, weights.cash_col)
        return materialize_effective_weights(weights=weights, prices=prices)

    def _data_to_prices(self, data: pl.DataFrame, assets: list[str], cash_col: str) -> pl.DataFrame:
        """Return wide prices ``[timestamp, ASSET..., CASH]`` from wide or panel data.

        Panel prices are forward-filled only (no look-ahead); pre-listing gaps get a
        neutral 1.0.
        """
        if all(asset in data.columns for asset in assets):
            prices = data.select(["timestamp"] + assets)
            if cash_col not in prices.columns:
                prices = prices.with_columns(pl.lit(1.0).alias(cash_col))
            return prices
        if "asset" in data.columns and "close" in data.columns:
            prices = (
                data.filter(pl.col("asset").is_in(assets))
                .pivot(values="close", index="timestamp", on="asset")
                .sort("timestamp")
            )
            asset_cols = [c for c in prices.columns if c != "timestamp"]
            return prices.with_columns(
                [pl.col(c).forward_fill().fill_null(1.0) for c in asset_cols] + [pl.lit(1.0).alias(cash_col)]
            )
        raise ValueError(
            "Data format not recognized. Expected either:\n"
            "  - Wide format: [timestamp, BTC, ETH, ...]\n"
            "  - Panel format: [timestamp, asset, close, ...]"
        )

    def _build_backtest_output(
        self,
        weights: StrategyWeights,
        result: "BacktestResult",
        run_id: str,
    ) -> BacktestOutput:
        """Build a serializable backtest payload from runner outputs."""
        equity_df = result.to_dataframe()
        timestamps = weights.weights["timestamp"]
        ledger = self.last_intent_result

        if ledger is not None and ledger.backtest is result and ledger.account.height == len(equity_df):
            # Intent-ledger equity has one row per market event, labelled by the account rows.
            equity_df = equity_df.with_columns(ledger.account["timestamp"])
        elif len(timestamps) == len(equity_df):
            equity_df = equity_df.with_columns(timestamps.alias("timestamp"))
        elif len(timestamps) == len(equity_df) + 1:
            equity_df = equity_df.with_columns(timestamps.slice(1).alias("timestamp"))

        data_range = None
        if timestamps.dtype == pl.Datetime:
            data_range = {"start": str(timestamps.min()), "end": str(timestamps.max())}

        cfg = self.run_config
        return BacktestOutput(
            strategy_id=cfg.strategy_id,
            run_id=run_id,
            equity=equity_df,
            metrics=dict(result.metrics),
            config=self.get_config_dict(),
            created_at=datetime.now(),
            data_range=data_range,
            training_metadata=self.get_training_metadata(),
            strategy_type=cfg.strategy_type,
            memory_version=cfg.memory_version,
            preset=cfg.preset_name or cfg.strategy_id,
        )


# --------------------------------------------------------------------------- #
# Run status
# --------------------------------------------------------------------------- #


class _RunStatus:
    """``status.json`` in a saved run directory: running, then succeeded or failed; inert without one."""

    def __init__(self, run_dir: Path | None, cfg: StrategyRunConfig, run_id: str | None) -> None:
        self.path = None if run_dir is None else run_dir / "status.json"
        self.phases: dict[str, float] = {}
        self.started = time.monotonic()
        self.record: dict[str, Any] = dict(
            run_id=run_id,
            strategy_type=cfg.strategy_type,
            memory_version=cfg.memory_version,
            preset=cfg.preset_name or cfg.strategy_id,
            strategy_id=cfg.strategy_id,
            state="running",
            started_at=datetime.now(UTC).isoformat(),
            pid=os.getpid(),
            host=socket.gethostname(),
        )
        self._write()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.phases[name] = round(time.monotonic() - start, 3)

    def finish(self, state: str, **fields: Any) -> None:
        self.record |= dict(
            state=state,
            finished_at=datetime.now(UTC).isoformat(),
            duration_s=round(time.monotonic() - self.started, 3),
            phases=self.phases,
            **fields,
        )
        self._write()

    def _write(self) -> None:
        if self.path is None:
            return
        temporary = self.path.with_name(f".status.json.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(self.record, indent=2, default=str) + "\n")
        temporary.replace(self.path)
