"""Backtest result container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

import polars as pl

from .result_schema import validate_result_dataframe

if TYPE_CHECKING:
    from execution import ExecutionResult, RestingLimitExecutionResult


@dataclass(frozen=True, slots=True)
class LedgerDetail:
    """Opt-in ordinary-ledger evidence (``BacktestConfig(collect_ledger_detail=True)``).

    Every value is one the ledger already computed for its interval ``[t_i, t_{i+1}]``;
    money is in account currency, quantities in asset units, timestamps are the input rows'.

    Attributes:
        positions: Non-zero holdings per interval at ``timestamp = t_i``:
            ``timestamp, asset, quantity, price, notional, weight`` (price ``p_i``,
            weight = notional / pre-trade equity).
        trades: Non-zero rebalance trades filled at ``timestamp = t_i``:
            ``timestamp, asset, side, quantity, price, notional, fee`` (signed quantity
            and notional; fee = |notional| × cost rate).
        asset_attribution: Every interval × asset, labelled ``timestamp = t_{i+1}``, the
            row whose equity books the interval: ``timestamp, asset, price, quantity, weight,
            price_pnl, funding_pnl, fees`` (price ``p_{i+1}``, quantity held through the
            interval, weight = marked notional / equity at ``t_{i+1}``, fees of the ``t_i``
            fill). ``initial_capital + cumsum(price_pnl + funding_pnl - fees)`` matches equity
            to floating-point rounding.
    """

    positions: pl.DataFrame
    trades: pl.DataFrame
    asset_attribution: pl.DataFrame


@dataclass(slots=True)
class BacktestResult:
    """Complete backtest result.

    Attributes:
        equity: Strategy equity curve.
        benchmark_equity: Buy-and-hold benchmark equity curve.
        price_return: Returns from price changes.
        funding_return: Returns from funding rates.
        cost_return: Transaction cost drag.
        net_return: Combined net returns.
        turnover: Portfolio turnover per period.
        metrics: Dict of computed metrics.
        execution: Opt-in ExecutionResult; None on legacy paths.
        resting_limit_execution: Deterministic OHLC result; None on other paths.
        ledger_detail: Opt-in ordinary-ledger positions, trades and cash flows; None otherwise.
    """

    equity: pl.Series
    benchmark_equity: pl.Series
    price_return: pl.Series
    funding_return: pl.Series
    cost_return: pl.Series
    net_return: pl.Series
    turnover: pl.Series
    metrics: Mapping[str, float]
    engine_used: str = "nautilus"
    engine_meta: dict[str, str | int | float | bool] = field(default_factory=dict)
    execution: ExecutionResult | None = None
    resting_limit_execution: RestingLimitExecutionResult | None = None
    ledger_detail: LedgerDetail | None = None

    def to_dataframe(self) -> pl.DataFrame:
        """Convert result series to a single DataFrame."""
        df = pl.DataFrame(
            {
                "equity": self.equity,
                "benchmark_equity": self.benchmark_equity,
                "price_return": pl.concat([pl.Series([0.0]), self.price_return]),
                "funding_return": pl.concat([pl.Series([0.0]), self.funding_return]),
                "cost_return": pl.concat([pl.Series([0.0]), self.cost_return]),
                "net_return": pl.concat([pl.Series([0.0]), self.net_return]),
                "turnover": pl.concat([pl.Series([0.0]), self.turnover]),
            }
        )
        validate_result_dataframe(df)
        return df

    def summary(self) -> str:
        """Generate a text summary of the backtest results."""
        lines = ["Backtest Results", "=" * 40]

        for name, value in self.metrics.items():
            if "return" in name or "share" in name:
                lines.append(f"{name}: {value:.2%}")
            elif "drawdown" in name:
                lines.append(f"{name}: {value:.2%}")
            elif "sharpe" in name or "calmar" in name:
                lines.append(f"{name}: {value:.2f}")
            else:
                lines.append(f"{name}: {value:.4f}")

        return "\n".join(lines)
