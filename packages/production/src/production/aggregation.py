"""Cash-flow-adjusted P&L, capital weights, and portfolio aggregation.

Purpose: turn per-strategy capital observations into the derived level series
and metrics a read-only telemetry projection publishes, without ever inferring
a number the observations do not support.

Three rules govern everything here:

* P&L is never a raw equity difference.  ``period_pnl = current_equity -
  previous_equity - net_external_cash_flow``.
* Portfolio return is chain-linked on summed equities, never an average of
  strategy returns.
* A missing or stale included member makes the aggregate explicitly
  incomplete.  It is never dropped so the remainder can be presented as a
  total.

USAGE::

    series = strategy_series(observations, max_age_seconds=172_800, now=now)
    points = aggregate_series(manifest, {"example-family": series}, now=now)
    metrics = performance_metrics(series.points)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from production.observation import (
    CapitalObservation,
    PortfolioManifest,
    lifecycle_state,
    overall_health,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

#: Trading days per year for annualization.  Crypto venues settle every day,
#: so the calendar year is the honest scaling factor.
ANNUALIZATION_DAYS = 365

#: Observation counts below which a metric is not supportable and returns
#: ``None`` so the UI can render an em dash instead of a manufactured zero.
MIN_RETURN_OBSERVATIONS = 1
MIN_PATH_OBSERVATIONS = 5
MIN_RISK_OBSERVATIONS = 20

COMPLETENESS_STATES: tuple[str, ...] = ("complete", "incomplete", "stale", "empty")


# --------------------------------------------------------------------------- #
# Core formulas
# --------------------------------------------------------------------------- #


def period_pnl(
    current_equity: Decimal,
    previous_equity: Decimal,
    net_external_cash_flow: Decimal,
) -> Decimal:
    """Return P&L over one interval with operator cash movement removed."""
    return current_equity - previous_equity - net_external_cash_flow


def interval_return(
    current_equity: Decimal,
    previous_equity: Decimal,
    net_external_cash_flow: Decimal,
) -> Decimal | None:
    """Return the interval return with flows credited at the interval start.

    ``None`` means the interval carries no supportable return: the capital base
    (previous equity plus the flow) is zero or negative, so a ratio would be
    meaningless rather than merely noisy.
    """
    base = previous_equity + net_external_cash_flow
    if base <= 0:
        return None
    return period_pnl(current_equity, previous_equity, net_external_cash_flow) / base


def chain_link(returns: Sequence[Decimal]) -> Decimal:
    """Compound interval returns into one cumulative return."""
    growth = Decimal("1")
    for value in returns:
        growth *= Decimal("1") + value
    return growth - Decimal("1")


def capital_weights(equity_by_family: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Return each family's share of total portfolio equity.

    A capital weight is strategy account equity divided by total portfolio
    equity.  It is not a strategy's internal target exposure, and it is never
    derived from an activation cap or a contract limit: those are safety
    authority, not capital allocation.  An empty result means total equity is
    not positive, so no weight is supportable.
    """
    total = sum(equity_by_family.values(), start=Decimal("0"))
    if total <= 0:
        return {}
    return {family: equity / total for family, equity in equity_by_family.items()}


# --------------------------------------------------------------------------- #
# Per-strategy series
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One UTC reporting boundary for one strategy."""

    day: date
    observed_at: datetime
    equity_usd: Decimal
    external_flow_usd: Decimal
    period_pnl_usd: Decimal | None
    interval_return: Decimal | None
    cum_pnl_usd: Decimal
    cum_return: Decimal | None


@dataclass(frozen=True, slots=True)
class StrategySeries:
    """A strategy's reporting-boundary history plus its freshness verdict.

    ``state`` is the deployment's lifecycle state and ``health`` its rolled-up
    check verdict; both come from the newest observation and are independent of
    whether capital history exists.
    """

    family: str
    points: tuple[SeriesPoint, ...]
    latest: CapitalObservation | None
    stale: bool
    max_age_seconds: int

    @property
    def has_capital(self) -> bool:
        """Return whether any capital observation backs this strategy."""
        return bool(self.points)

    @property
    def equity_usd(self) -> Decimal | None:
        """Return the newest observed account equity, if any."""
        return self.points[-1].equity_usd if self.points else None

    @property
    def state(self) -> str | None:
        """Return the lifecycle state from the newest observation."""
        return None if self.latest is None else lifecycle_state(self.latest.authority_facts)

    @property
    def health(self) -> str | None:
        """Return the rolled-up health verdict from the newest observation."""
        if self.latest is None:
            return None
        return overall_health(self.latest.health_checks, self.latest.authority_facts)

    @property
    def usable(self) -> bool:
        """Return whether this strategy may contribute to an aggregate total."""
        return self.has_capital and not self.stale


def _reporting_boundaries(
    observations: Sequence[CapitalObservation],
) -> tuple[tuple[date, CapitalObservation, Decimal], ...]:
    """Collapse observations onto UTC days, summing flows within each day.

    The last observation of a UTC day is that day's mark.  Flows recorded by
    superseded observations on the same day still happened, so they are summed
    into the day's flow rather than discarded with the superseded mark.
    """
    ordered = sorted(observations, key=lambda item: item.observed_at)
    by_day: dict[date, list[CapitalObservation]] = {}
    for observation in ordered:
        by_day.setdefault(observation.observed_at.astimezone(UTC).date(), []).append(observation)
    return tuple(
        (
            day,
            entries[-1],
            sum(
                (entry.external_flow_usd_since_previous for entry in entries),
                start=Decimal("0"),
            ),
        )
        for day, entries in sorted(by_day.items())
    )


def strategy_series(
    family: str,
    observations: Sequence[CapitalObservation],
    *,
    max_age_seconds: int,
    now: datetime,
) -> StrategySeries:
    """Build one strategy's reporting-boundary series and freshness verdict."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    boundaries = _reporting_boundaries(observations)
    points: list[SeriesPoint] = []
    cum_pnl = Decimal("0")
    returns: list[Decimal] = []
    return_broken = False
    previous_equity: Decimal | None = None
    for day, observation, flow in boundaries:
        if previous_equity is None:
            # Inception: the first mark defines the baseline, not a gain.
            pnl: Decimal | None = None
            step: Decimal | None = None
        else:
            pnl = period_pnl(observation.equity_usd, previous_equity, flow)
            step = interval_return(observation.equity_usd, previous_equity, flow)
            cum_pnl += pnl
            if step is None:
                return_broken = True
            else:
                returns.append(step)
        points.append(
            SeriesPoint(
                day=day,
                observed_at=observation.observed_at,
                equity_usd=observation.equity_usd,
                external_flow_usd=flow,
                period_pnl_usd=pnl,
                interval_return=step,
                cum_pnl_usd=cum_pnl,
                cum_return=None if return_broken else chain_link(returns),
            )
        )
        previous_equity = observation.equity_usd
    latest = boundaries[-1][1] if boundaries else None
    stale = latest is None or (now.astimezone(UTC) - latest.observed_at > timedelta(seconds=max_age_seconds))
    return StrategySeries(
        family=family,
        points=tuple(points),
        latest=latest,
        stale=stale,
        max_age_seconds=max_age_seconds,
    )


# --------------------------------------------------------------------------- #
# Portfolio aggregation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AggregatePoint:
    """One portfolio reporting boundary.

    Levels are ``None`` on any day where an included member has no mark.  The
    aggregate refuses to invent a total from a subset, and it refuses to carry
    a stale equity forward as if it had been observed.
    """

    day: date
    equity_usd: Decimal | None
    cum_pnl_usd: Decimal | None
    cum_return: Decimal | None
    period_pnl_usd: Decimal | None
    period_return: Decimal | None
    complete: bool
    missing: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioAggregate:
    """The portfolio-level projection over every included member."""

    portfolio_id: str
    points: tuple[AggregatePoint, ...]
    completeness: str
    included_families: tuple[str, ...]
    missing_families: tuple[str, ...]
    stale_families: tuple[str, ...]
    equity_usd: Decimal | None
    weights: dict[str, Decimal]

    @property
    def complete(self) -> bool:
        """Return whether every included member contributed fresh capital."""
        return self.completeness == "complete"


def aggregate_series(
    manifest: PortfolioManifest,
    series_by_family: Mapping[str, StrategySeries],
    *,
    now: datetime,
) -> PortfolioAggregate:
    """Aggregate included members into a chain-linked portfolio series.

    Each member's interval is measured against *its own* previous mark, so a
    member's ``external_flow_usd_since_previous`` always spans exactly the
    interval it is applied to — even across days the portfolio could not
    complete.
    """
    included = [member.family for member in manifest.included_members]
    missing = tuple(
        family for family in included if family not in series_by_family or not series_by_family[family].has_capital
    )
    stale = tuple(
        family
        for family in included
        if family in series_by_family and series_by_family[family].has_capital and series_by_family[family].stale
    )

    marks: dict[str, dict[date, SeriesPoint]] = {}
    days: set[date] = set()
    for family in included:
        series = series_by_family.get(family)
        if series is None:
            continue
        marks[family] = {point.day: point for point in series.points}
        days.update(marks[family])

    points: list[AggregatePoint] = []
    cum_pnl = Decimal("0")
    returns: list[Decimal] = []
    return_broken = False
    previous_marks: dict[str, SeriesPoint] = {}
    for day in sorted(days):
        present = {family: marks.get(family, {}).get(day) for family in included}
        absent = tuple(family for family, mark in present.items() if mark is None)
        if absent:
            points.append(
                AggregatePoint(
                    day=day,
                    equity_usd=None,
                    cum_pnl_usd=None,
                    cum_return=None,
                    period_pnl_usd=None,
                    period_return=None,
                    complete=False,
                    missing=absent,
                )
            )
            # Marks observed on an incomplete day still update each member's
            # own previous mark, so the next complete interval is not skewed.
            for family, mark in present.items():
                if mark is not None:
                    previous_marks[family] = mark
            continue

        equity = sum((mark.equity_usd for mark in present.values() if mark), start=Decimal("0"))
        if len(previous_marks) < len(included):
            # Inception boundary: baseline the portfolio without claiming P&L.
            step_pnl: Decimal | None = None
            step_return: Decimal | None = None
        else:
            previous_equity = sum((previous_marks[family].equity_usd for family in included), start=Decimal("0"))
            flow = sum((mark.external_flow_usd for mark in present.values() if mark), start=Decimal("0"))
            step_pnl = period_pnl(equity, previous_equity, flow)
            step_return = interval_return(equity, previous_equity, flow)
            cum_pnl += step_pnl
            if step_return is None:
                return_broken = True
            else:
                returns.append(step_return)
        points.append(
            AggregatePoint(
                day=day,
                equity_usd=equity,
                cum_pnl_usd=cum_pnl,
                cum_return=None if return_broken else chain_link(returns),
                period_pnl_usd=step_pnl,
                period_return=step_return,
                complete=True,
                missing=(),
            )
        )
        for family, mark in present.items():
            if mark is not None:
                previous_marks[family] = mark

    if not included:
        completeness = "empty"
    elif missing:
        completeness = "empty" if len(missing) == len(included) else "incomplete"
    elif stale:
        completeness = "stale"
    else:
        completeness = "complete"

    usable_equity = {
        family: series_by_family[family].equity_usd
        for family in included
        if family in series_by_family and series_by_family[family].equity_usd is not None
    }
    equity_usd = sum(usable_equity.values(), start=Decimal("0")) if completeness == "complete" else None
    weights = (
        capital_weights({family: value for family, value in usable_equity.items() if value is not None})
        if completeness == "complete"
        else {}
    )
    return PortfolioAggregate(
        portfolio_id=manifest.portfolio_id,
        points=tuple(points),
        completeness=completeness,
        included_families=tuple(included),
        missing_families=missing,
        stale_families=stale,
        equity_usd=equity_usd,
        weights=weights,
    )


# --------------------------------------------------------------------------- #
# Performance metrics
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    """Metrics with explicit nulls wherever observations cannot support them."""

    total_pnl_usd: Decimal | None
    total_return: Decimal | None
    max_drawdown: Decimal | None
    annualized_volatility: Decimal | None
    sharpe: Decimal | None
    positive_day_rate: Decimal | None
    observation_count: int


def _sample_std(values: Sequence[Decimal], mean: Decimal) -> Decimal | None:
    if len(values) < 2:
        return None
    variance = sum(((value - mean) ** 2 for value in values), start=Decimal("0")) / (len(values) - 1)
    if variance <= 0:
        return None
    return variance.sqrt()


def performance_metrics(
    points: Sequence[SeriesPoint] | Sequence[AggregatePoint],
) -> PerformanceMetrics:
    """Compute metrics from reporting boundaries, returning None when unsupported.

    Only intervals are evidence: a series with a single mark has an equity level
    but no return, and reports every metric as ``None`` rather than zero.
    Aggregate boundaries contribute only where they are complete, so a gap
    neither fabricates a flat day nor a jump across the gap.
    """
    returns = _interval_returns(points)
    pnls = [
        point.period_pnl_usd
        for point in points
        if point.period_pnl_usd is not None and (not isinstance(point, AggregatePoint) or point.complete)
    ]

    count = len(returns)
    total_pnl = sum(pnls, start=Decimal("0")) if pnls else None
    total_return = chain_link(returns) if count >= MIN_RETURN_OBSERVATIONS else None

    max_drawdown: Decimal | None = None
    positive_rate: Decimal | None = None
    if count >= MIN_PATH_OBSERVATIONS:
        level = Decimal("1")
        peak = Decimal("1")
        trough = Decimal("0")
        for value in returns:
            level *= Decimal("1") + value
            peak = max(peak, level)
            if peak > 0:
                trough = min(trough, level / peak - Decimal("1"))
        max_drawdown = trough
        positive_rate = Decimal(sum(1 for value in returns if value > 0)) / Decimal(count)

    volatility: Decimal | None = None
    sharpe: Decimal | None = None
    if count >= MIN_RISK_OBSERVATIONS:
        mean = sum(returns, start=Decimal("0")) / Decimal(count)
        std = _sample_std(returns, mean)
        if std is not None:
            scale = Decimal(ANNUALIZATION_DAYS).sqrt()
            volatility = std * scale
            sharpe = (mean / std) * scale

    return PerformanceMetrics(
        total_pnl_usd=total_pnl,
        total_return=total_return,
        max_drawdown=max_drawdown,
        annualized_volatility=volatility,
        sharpe=sharpe,
        positive_day_rate=positive_rate,
        observation_count=count,
    )


def _interval_returns(points: Sequence[SeriesPoint] | Sequence[AggregatePoint]) -> list[Decimal]:
    """Return the supportable interval returns carried by these boundaries."""
    if points and isinstance(points[0], AggregatePoint):
        return _aggregate_returns(cast(Sequence[AggregatePoint], points))
    return [
        point.interval_return
        for point in points
        if isinstance(point, SeriesPoint) and point.interval_return is not None
    ]


def _aggregate_returns(points: Sequence[AggregatePoint]) -> list[Decimal]:
    """Return the interval returns the aggregate actually measured."""
    return [point.period_return for point in points if point.complete and point.period_return is not None]


__all__ = [
    "ANNUALIZATION_DAYS",
    "COMPLETENESS_STATES",
    "MIN_PATH_OBSERVATIONS",
    "MIN_RETURN_OBSERVATIONS",
    "MIN_RISK_OBSERVATIONS",
    "AggregatePoint",
    "PerformanceMetrics",
    "PortfolioAggregate",
    "SeriesPoint",
    "StrategySeries",
    "aggregate_series",
    "capital_weights",
    "chain_link",
    "interval_return",
    "performance_metrics",
    "period_pnl",
    "strategy_series",
]
