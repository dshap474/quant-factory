"""Matplotlib drawing and atomic PNG output for execution charts.

Purpose: render validated execution chart semantics without owning ledger or
market-data validation.

USAGE:
    >>> path = render_chart_data(data, output=Path("execution.png"), overwrite=False)  # doctest: +SKIP
"""

from __future__ import annotations

import math
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import matplotlib.dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .api import _ExecutionChartData, _RawFill

if TYPE_CHECKING:
    from matplotlib.axes import Axes

# --------------------------------------------------------------------------- #
# Atomic PNG output
# --------------------------------------------------------------------------- #

_PNG_WIDTH = 1600
_PNG_HEIGHT = 900
_PNG_DPI = 150


def render_chart_data(data: _ExecutionChartData, *, output: Path, overwrite: bool) -> Path:
    """Draw validated chart data and atomically publish one PNG."""
    if not isinstance(output, Path):
        raise TypeError("output must be Path")
    if output.suffix.lower() != ".png":
        raise ValueError("output must use a .png suffix")
    destination = output.resolve()
    if destination.exists() and not overwrite:
        raise FileExistsError(f"execution chart already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")

    figure = Figure(
        figsize=(_PNG_WIDTH / _PNG_DPI, _PNG_HEIGHT / _PNG_DPI),
        dpi=_PNG_DPI,
    )
    FigureCanvasAgg(figure)
    axes = figure.subplots(
        2,
        1,
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1], "hspace": 0.08},
    )
    try:
        _draw_price_panel(axes[0], data)
        _draw_trajectory_panel(axes[1], data)
        figure.suptitle(data.title, fontsize=14, fontweight="bold")
        if data.footer:
            figure.text(0.01, 0.01, data.footer, fontsize=7, color="#64748b")
        figure.savefig(
            temporary,
            format="png",
            dpi=_PNG_DPI,
            facecolor="white",
            bbox_inches=None,
            metadata={"Software": "quant-factory"},
        )
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
    finally:
        figure.clear()
        temporary.unlink(missing_ok=True)
    return destination


# --------------------------------------------------------------------------- #
# Price and fill panel
# --------------------------------------------------------------------------- #


def _draw_price_panel(axis: Axes, data: _ExecutionChartData) -> None:
    from matplotlib.patches import Rectangle

    timestamps = data.bars.get_column("ts_init").to_list()
    numbers = mdates.date2num(timestamps)
    width = _candle_width(numbers)
    for number, row in zip(numbers, data.bars.iter_rows(named=True), strict=True):
        open_price = float(row["open"])
        close_price = float(row["close"])
        color = "#16a34a" if close_price >= open_price else "#dc2626"
        axis.vlines(number, float(row["low"]), float(row["high"]), color=color, linewidth=0.8)
        height = max(abs(close_price - open_price), max(open_price, close_price) * 1e-7)
        axis.add_patch(
            Rectangle(
                (number - width / 2, min(open_price, close_price)),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                alpha=0.72,
            )
        )
    axis.axhline(float(data.decision_price), color="#64748b", linestyle=":", linewidth=1, label="Decision")
    axis.axhline(float(data.arrival_price), color="#94a3b8", linestyle="--", linewidth=1, label="Arrival")
    if data.fill_vwap is not None:
        axis.axhline(float(data.fill_vwap), color="#2563eb", linestyle="-.", linewidth=1, label="Fill VWAP")
    _draw_fill_markers(axis, data)
    axis.set_ylabel("Price")
    axis.grid(alpha=0.16)
    axis.legend(loc="best", fontsize=8, ncols=3)


def _draw_fill_markers(axis: Axes, data: _ExecutionChartData) -> None:
    grouped: dict[tuple[datetime, int], list[_RawFill]] = {}
    for fill in data.fills:
        side = 1 if fill.quantity > 0 else -1
        grouped.setdefault((fill.filled_at, side), []).append(fill)
    total = sum((abs(fill.quantity * fill.price * data.multiplier) for fill in data.fills), Decimal(0))
    labeled_sides: set[int] = set()
    for (timestamp, side), fills in grouped.items():
        quantity = sum((abs(fill.quantity) for fill in fills), Decimal(0))
        price = sum((abs(fill.quantity) * fill.price for fill in fills), Decimal(0)) / quantity
        notional = sum((abs(fill.quantity * fill.price * data.multiplier) for fill in fills), Decimal(0))
        share = float(notional / total) if total else 0.0
        size = 35 + 100 * math.sqrt(share)
        label = ("Buy fill" if side > 0 else "Sell fill") if side not in labeled_sides else "_nolegend_"
        labeled_sides.add(side)
        axis.scatter(
            [mdates.date2num(timestamp)],
            [float(price)],
            marker="^" if side > 0 else "v",
            s=size,
            color="#15803d" if side > 0 else "#b91c1c",
            edgecolor="white",
            linewidth=0.7,
            zorder=5,
            label=label,
        )


# --------------------------------------------------------------------------- #
# Cumulative trajectory panel
# --------------------------------------------------------------------------- #


def _draw_trajectory_panel(axis: Axes, data: _ExecutionChartData) -> None:
    axis.step(
        mdates.date2num(list(data.actual_times)),
        [float(value) for value in data.actual_notionals],
        where="post",
        color="#2563eb",
        linewidth=1.8,
        label="Actual notional",
        zorder=2,
    )
    axis.step(
        mdates.date2num(list(data.planned_times)),
        [float(value) for value in data.planned_notionals],
        where="post",
        color="#64748b",
        linestyle="--",
        linewidth=1.4,
        label="Planned notional",
        zorder=3,
    )
    summary = (
        f"Completion {float(data.completion_ratio):.1%}  |  "
        f"Executed {float(data.actual_notionals[-1]):,.0f} USDT  |  "
        f"Fills {len(data.fills)}  |  Fees {float(data.total_fee):,.2f} USDT  |  "
        f"Shortfall {float(data.shortfall_bps):.2f} bps"
    )
    axis.text(0.01, 0.95, summary, transform=axis.transAxes, va="top", fontsize=8, color="#334155")
    axis.set_ylabel("Cumulative notional")
    axis.set_xlabel("UTC")
    duration = (data.terminal_at - data.decision_at).total_seconds()
    axis.xaxis.set_major_formatter(
        mdates.DateFormatter("%H:%M:%S" if duration <= 300 else "%H:%M", tz=UTC)
    )
    axis.grid(alpha=0.16)
    axis.legend(loc="lower right", fontsize=8)


def _candle_width(numbers: Sequence[float]) -> float:
    gaps = [right - left for left, right in zip(numbers, numbers[1:], strict=False) if right > left]
    return (min(gaps) if gaps else 1 / (24 * 60)) * 0.65


__all__ = ["render_chart_data"]
