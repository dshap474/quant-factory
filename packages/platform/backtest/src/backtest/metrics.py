"""Performance metrics for backtest evaluation.

USAGE: compute_metrics(context, ["sharpe", "sortino"])
"""

from dataclasses import dataclass
from math import sqrt
from typing import Callable, Protocol

import numpy as np

from .config import get_annualization_factor
from .path_metrics import sortino_ratio


@dataclass(slots=True)
class MetricContext:
    """Context provided to metric functions.

    Contains all the data needed to compute any metric.
    """

    equity: np.ndarray  # Equity curve, shape (T,)
    net_return: np.ndarray  # Net returns, shape (T-1,)
    price_return: np.ndarray  # Price returns, shape (T-1,)
    benchmark_return: np.ndarray  # Benchmark returns, shape (T-1,)
    funding_return: np.ndarray  # Funding returns, shape (T-1,)
    cost_return: np.ndarray  # Cost returns, shape (T-1,)
    turnover: np.ndarray  # Turnover, shape (T-1,)
    frequency: str  # Data frequency for annualization


class Metric(Protocol):
    """Protocol for metric functions."""

    name: str

    def __call__(self, ctx: MetricContext) -> float:
        """Compute the metric value."""
        ...


# --------------------------------------------------------------------------- #
# Metric implementations
# --------------------------------------------------------------------------- #


def _annualization_factor(ctx: MetricContext) -> float:
    return get_annualization_factor(ctx.frequency)


def _annualized_return(returns: np.ndarray, factor: float) -> float:
    if len(returns) == 0:
        return 0.0
    return float(np.mean(returns) * factor)


def _annualized_volatility(returns: np.ndarray, factor: float) -> float:
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns, ddof=1) * sqrt(factor))


def _active_returns(ctx: MetricContext) -> np.ndarray:
    if len(ctx.net_return) == 0 or len(ctx.benchmark_return) == 0:
        return np.array([], dtype=np.float64)
    return ctx.net_return - ctx.benchmark_return


def _sharpe_value(ctx: MetricContext) -> float:
    factor = _annualization_factor(ctx)
    ann_return = _annualized_return(ctx.net_return, factor)
    ann_vol = _annualized_volatility(ctx.net_return, factor)
    if ann_vol == 0:
        return 0.0
    return float(ann_return / ann_vol)


def _lag1_autocorrelation(values: np.ndarray) -> float | None:
    if len(values) < 3:
        return None

    x = values[:-1]
    y = values[1:]

    if np.std(x) == 0 or np.std(y) == 0:
        return None

    rho1 = np.corrcoef(x, y)[0, 1]
    if not np.isfinite(rho1):
        return None
    return float(rho1)


class TotalReturnMetric:
    """Total cumulative return."""

    name = "total_return"

    def __call__(self, ctx: MetricContext) -> float:
        if len(ctx.equity) < 2:
            return 0.0
        return float(ctx.equity[-1] / ctx.equity[0] - 1.0)


class AnnualizedReturnMetric:
    """Annualized return (mean return × annualization factor)."""

    name = "ann_return"

    def __call__(self, ctx: MetricContext) -> float:
        return _annualized_return(ctx.net_return, _annualization_factor(ctx))


class AnnualizedVolatilityMetric:
    """Annualized volatility (std × sqrt(factor))."""

    name = "ann_vol"

    def __call__(self, ctx: MetricContext) -> float:
        return _annualized_volatility(ctx.net_return, _annualization_factor(ctx))


class SharpeMetric:
    """Sharpe ratio (annualized return / annualized volatility)."""

    name = "sharpe"

    def __call__(self, ctx: MetricContext) -> float:
        return _sharpe_value(ctx)


class SortinoMetric:
    """Sortino ratio (annualized return / downside volatility)."""

    name = "sortino"

    def __call__(self, ctx: MetricContext) -> float:
        # Keep the engine's legacy zero sentinel for undefined ratios.
        value = sortino_ratio(ctx.net_return, periods_per_year=_annualization_factor(ctx))
        return value if value is not None else 0.0


class MaxDrawdownMetric:
    """Maximum drawdown (largest peak-to-trough decline)."""

    name = "max_drawdown"

    def __call__(self, ctx: MetricContext) -> float:
        if len(ctx.equity) < 2:
            return 0.0

        # Running maximum
        running_max = np.maximum.accumulate(ctx.equity)

        # Drawdown at each point
        drawdowns = ctx.equity / running_max - 1.0

        # Maximum drawdown (most negative value, returned as positive)
        return float(abs(drawdowns.min()))


class ActiveReturnMetric:
    """Annualized active return relative to the configured benchmark."""

    name = "active_return"

    def __call__(self, ctx: MetricContext) -> float:
        return _annualized_return(_active_returns(ctx), _annualization_factor(ctx))


class TrackingErrorMetric:
    """Annualized tracking error of active returns."""

    name = "tracking_error"

    def __call__(self, ctx: MetricContext) -> float:
        return _annualized_volatility(_active_returns(ctx), _annualization_factor(ctx))


class InformationRatioMetric:
    """Portfolio information ratio using active return over tracking error."""

    name = "information_ratio"

    def __call__(self, ctx: MetricContext) -> float:
        active_return = ActiveReturnMetric()(ctx)
        tracking_error = TrackingErrorMetric()(ctx)
        if tracking_error == 0:
            return 0.0
        return float(active_return / tracking_error)


class AverageTurnoverMetric:
    """Average portfolio turnover per period."""

    name = "avg_turnover"

    def __call__(self, ctx: MetricContext) -> float:
        if len(ctx.turnover) == 0:
            return 0.0
        return float(np.mean(ctx.turnover))


class FundingShareMetric:
    """Fraction of total P&L attributable to funding rates."""

    name = "funding_share"

    def __call__(self, ctx: MetricContext) -> float:
        price_sum = np.sum(ctx.price_return)
        funding_sum = np.sum(ctx.funding_return)
        cost_sum = np.sum(ctx.cost_return)

        total_pnl = price_sum + funding_sum - cost_sum

        if total_pnl == 0:
            return 0.0

        return float(funding_sum / total_pnl)


class WinRateMetric:
    """Fraction of periods with positive returns."""

    name = "win_rate"

    def __call__(self, ctx: MetricContext) -> float:
        if len(ctx.net_return) == 0:
            return 0.0
        return float(np.mean(ctx.net_return > 0))


class CalmarMetric:
    """Calmar ratio (annualized return / max drawdown)."""

    name = "calmar"

    def __call__(self, ctx: MetricContext) -> float:
        if len(ctx.net_return) < 2:
            return 0.0

        factor = get_annualization_factor(ctx.frequency)
        ann_return = np.mean(ctx.net_return) * factor

        running_max = np.maximum.accumulate(ctx.equity)
        drawdowns = ctx.equity / running_max - 1.0
        max_dd = abs(drawdowns.min())

        if max_dd == 0:
            return 0.0

        return float(ann_return / max_dd)


class SharpeStandardErrorMetric:
    """Standard error of the annualized Sharpe estimator.

    Lo (2002) iid SE of the per-period Sharpe, sqrt((1 + SR_p^2 / 2) / T), scaled by
    sqrt(q) like the Sharpe itself: sqrt((q + SR_ann^2 / 2) / T) for q periods a year.
    """

    name = "sharpe_se"

    def __call__(self, ctx: MetricContext) -> float:
        sample_size = len(ctx.net_return)
        if sample_size < 2:
            return 0.0

        sharpe = _sharpe_value(ctx)
        factor = get_annualization_factor(ctx.frequency)
        return float(sqrt((factor + sharpe**2 / 2.0) / sample_size))


class SharpeTStatMetric:
    """Approximate t-statistic of the Sharpe estimator."""

    name = "sharpe_tstat"

    def __call__(self, ctx: MetricContext) -> float:
        sharpe = _sharpe_value(ctx)
        sharpe_se = SharpeStandardErrorMetric()(ctx)
        if sharpe_se == 0:
            return 0.0
        return float(sharpe / sharpe_se)


class SharpeCILowerMetric:
    """Lower 95% confidence interval bound for Sharpe."""

    name = "sharpe_ci_lower"

    def __call__(self, ctx: MetricContext) -> float:
        sharpe = _sharpe_value(ctx)
        sharpe_se = SharpeStandardErrorMetric()(ctx)
        if sharpe_se == 0:
            return 0.0
        return float(sharpe - 1.96 * sharpe_se)


class SharpeCIUpperMetric:
    """Upper 95% confidence interval bound for Sharpe."""

    name = "sharpe_ci_upper"

    def __call__(self, ctx: MetricContext) -> float:
        sharpe = _sharpe_value(ctx)
        sharpe_se = SharpeStandardErrorMetric()(ctx)
        if sharpe_se == 0:
            return 0.0
        return float(sharpe + 1.96 * sharpe_se)


class SharpeAdjustedAutocorrelationMetric:
    """Lag-1 autocorrelation-adjusted Sharpe."""

    name = "sharpe_adj_autocorr"

    def __call__(self, ctx: MetricContext) -> float:
        sharpe = _sharpe_value(ctx)
        rho1 = _lag1_autocorrelation(ctx.net_return)
        if rho1 is None:
            return 0.0

        denominator = 1.0 + rho1
        numerator = 1.0 - rho1
        if denominator <= 0 or numerator < 0:
            return 0.0

        adjustment = numerator / denominator
        if adjustment < 0:
            return 0.0

        return float(sharpe * sqrt(adjustment))


# --- Metric Registry ---

METRIC_REGISTRY: dict[str, Callable[[], Metric]] = {
    "total_return": TotalReturnMetric,
    "ann_return": AnnualizedReturnMetric,
    "ann_vol": AnnualizedVolatilityMetric,
    "sharpe": SharpeMetric,
    "sortino": SortinoMetric,
    "max_drawdown": MaxDrawdownMetric,
    "active_return": ActiveReturnMetric,
    "tracking_error": TrackingErrorMetric,
    "information_ratio": InformationRatioMetric,
    "avg_turnover": AverageTurnoverMetric,
    "funding_share": FundingShareMetric,
    "win_rate": WinRateMetric,
    "calmar": CalmarMetric,
    "sharpe_se": SharpeStandardErrorMetric,
    "sharpe_tstat": SharpeTStatMetric,
    "sharpe_ci_lower": SharpeCILowerMetric,
    "sharpe_ci_upper": SharpeCIUpperMetric,
    "sharpe_adj_autocorr": SharpeAdjustedAutocorrelationMetric,
}


def compute_metrics(ctx: MetricContext, metric_names: list[str] | None = None) -> dict[str, float]:
    """Compute specified metrics.

    Args:
        ctx: MetricContext with all data.
        metric_names: List of metric names to compute. If None, computes all.

    Returns:
        Dict mapping metric names to values.
    """
    if metric_names is None:
        metric_names = list(METRIC_REGISTRY.keys())

    results = {}
    for name in metric_names:
        if name not in METRIC_REGISTRY:
            raise ValueError(f"Unknown metric: {name}. Available: {list(METRIC_REGISTRY.keys())}")
        metric = METRIC_REGISTRY[name]()
        results[name] = metric(ctx)

    return results
