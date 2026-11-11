"""Read-only single-asset attribution from selected-run ledgers.

USAGE::

    payload = load_single_asset_view(db_root, "strategy-family", "v001", asset="BTC")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from data.query import ParquetQuery, get_parquet_metadata, query_parquet
from strategies.contracts import validate_identifier, validate_memory_version

_RETURN_COLUMNS = (
    "timestamp",
    "equity",
    "benchmark_equity",
    "price_return",
    "funding_return",
    "cost_return",
    "net_return",
    "turnover",
)
_PERFORMANCE_COLUMNS = ("date", "strategy_daily_return", "strategy_portfolio_value")
_LEDGER_PAIRS = (
    ("effective_weights.parquet", "net_returns.parquet", 1),
    ("scheduled_target_weights.parquet", "scheduled_net_returns.parquet", None),
)


# --------------------------------------------------------------------------- #
# Errors and contracts
# --------------------------------------------------------------------------- #


class SingleAssetIntegrityError(ValueError):
    """Selected-run evidence is present but fails identity or accounting checks."""


class SingleAssetSelectionError(ValueError):
    """The requested asset is outside the selected run's universe."""


@dataclass(frozen=True)
class SelectedLedger:
    """Selected ordinary-ledger artifact paths and scalar configuration."""

    strategy_type: str
    memory_version: str
    run_id: str
    experiment: str
    title: str
    benchmark_id: str | None
    run_root: Path
    target_name: str
    returns_name: str
    performance_path: str
    asset_names: tuple[str, ...]
    initial_capital: float
    cost_bps: float
    rebalance_every_bars: int


@dataclass(frozen=True)
class SelectedAttribution:
    """Declared daily actual-account attribution, independent of strategy family."""

    manifest: dict[str, Any]
    metadata: dict[str, Any]
    path: Path


# --------------------------------------------------------------------------- #
# Evidence helpers
# --------------------------------------------------------------------------- #


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SingleAssetIntegrityError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise SingleAssetIntegrityError(f"{label} must be a JSON object")
    return value


def _require_safe_file(path: Path, root: Path, *, label: str) -> Path:
    root = root.resolve()
    unresolved = path.absolute()
    try:
        unresolved.relative_to(root)
        target = unresolved.resolve()
        target.relative_to(root)
    except ValueError as exc:
        raise SingleAssetIntegrityError(f"{label} escapes the research store") from exc
    current = unresolved
    while current != root:
        if current.is_symlink():
            raise SingleAssetIntegrityError(f"{label} cannot traverse symlinks")
        current = current.parent
    if not target.is_file():
        raise SingleAssetIntegrityError(f"{label} is missing")
    return target


def _resolve_inside(root: Path, relative: str, *, label: str, store_root: Path) -> Path:
    if not relative or Path(relative).is_absolute():
        raise SingleAssetIntegrityError(f"{label} must be a relative path")
    unresolved = root / relative
    target = unresolved.resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise SingleAssetIntegrityError(f"{label} escapes its selected version") from exc
    return _require_safe_file(unresolved, store_root, label=label)


def _finite_number(value: Any, *, label: str, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise SingleAssetIntegrityError(f"{label} must be finite")
    number = float(value)
    if positive and number <= 0:
        raise SingleAssetIntegrityError(f"{label} must be positive")
    return number


def _load_selected_ledger(
    db_root: Path,
    strategy_type: str,
    memory_version: str,
    *,
    expected_run_id: str | None,
) -> SelectedLedger | SelectedAttribution | None:
    validate_identifier(strategy_type, "strategy_type")
    validate_memory_version(memory_version)
    db_root = Path(db_root).resolve()
    research_root = (db_root / "research").resolve()
    version_root = research_root / "strategies" / strategy_type / memory_version
    pointer_path = version_root / "surface.json"
    if not pointer_path.is_file():
        return None
    _require_safe_file(pointer_path, research_root, label="selected surface pointer")

    pointer = _read_object(pointer_path, label="selected surface pointer")
    if (
        pointer.get("schema_version") != 1
        or pointer.get("strategy_type") != strategy_type
        or pointer.get("memory_version") != memory_version
    ):
        raise SingleAssetIntegrityError("selected surface pointer identity does not match the request")
    manifest_relative = pointer.get("selected_manifest")
    if not isinstance(manifest_relative, str):
        raise SingleAssetIntegrityError("selected surface pointer is incomplete")
    manifest_path = _resolve_inside(
        version_root,
        manifest_relative,
        label="selected manifest",
        store_root=research_root,
    )

    manifest = _read_object(manifest_path, label="selected manifest")
    run_id = manifest.get("run_id")
    experiment = manifest.get("experiment")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("strategy_type") != strategy_type
        or manifest.get("memory_version") != memory_version
        or not isinstance(run_id, str)
        or not isinstance(experiment, str)
        or not run_id
        or not experiment
    ):
        raise SingleAssetIntegrityError("selected manifest identity does not match the request")
    if expected_run_id is not None and run_id != expected_run_id:
        raise SingleAssetIntegrityError("selected run changed while the version was being read")

    run_root = manifest_path.parent.parent
    if run_root.name != run_id or run_root.parent.name != experiment:
        raise SingleAssetIntegrityError("selected manifest path does not match its run identity")
    if "attribution" in manifest:
        meta = manifest["attribution"]
        if not isinstance(meta, dict) or meta.get("contract") != "asset_attribution_v1" or not isinstance(meta.get("path"), str):
            raise SingleAssetIntegrityError("unsupported attribution contract")
        path = _resolve_inside(version_root, meta["path"], label="asset attribution", store_root=research_root)
        if not path.is_relative_to(run_root):
            raise SingleAssetIntegrityError("asset attribution is outside the selected run")
        return SelectedAttribution(manifest, meta, path)
    artifacts_path = run_root / "artifacts.json"
    if not artifacts_path.exists() and not artifacts_path.is_symlink():
        return None
    _require_safe_file(artifacts_path, research_root, label="artifact manifest")
    artifacts = _read_object(artifacts_path, label="artifact manifest")

    declared_pairs: list[tuple[str, str, int | None]] = []
    for target_name, returns_name, required_cadence in _LEDGER_PAIRS:
        target_declared = target_name in artifacts
        returns_declared = returns_name in artifacts
        if target_declared != returns_declared:
            raise SingleAssetIntegrityError("selected ledger has an unpaired target/return artifact")
        if target_declared:
            declared_pairs.append((target_name, returns_name, required_cadence))
    if not declared_pairs:
        return None
    if len(declared_pairs) != 1:
        raise SingleAssetIntegrityError("selected ledger has ambiguous target/return artifacts")

    config_path = run_root / "config.json"
    for name in ("config.json", "prices.parquet"):
        _require_safe_file(run_root / name, research_root, label=f"selected artifact {name}")
    config = _read_object(config_path, label="selected run config")

    configured_cadence = config.get("rebalance_every_bars", 1)
    if not isinstance(configured_cadence, int) or isinstance(configured_cadence, bool):
        raise SingleAssetIntegrityError("rebalance_every_bars must be an integer")
    target_name, returns_name, required_cadence = declared_pairs[0]
    if required_cadence is not None and configured_cadence != required_cadence:
        raise SingleAssetIntegrityError("selected ledger cadence conflicts with its artifact contract")
    if required_cadence is None and configured_cadence <= 1:
        raise SingleAssetIntegrityError("scheduled ledger requires rebalance_every_bars above one")
    cadence = configured_cadence

    for name in (target_name, returns_name):
        _require_safe_file(run_root / name, research_root, label=f"selected artifact {name}")

    performance = manifest.get("performance")
    if not isinstance(performance, dict):
        raise SingleAssetIntegrityError("selected manifest has no performance artifact")
    performance_relative = performance.get("path")
    if not isinstance(performance_relative, str):
        raise SingleAssetIntegrityError("selected performance metadata is incomplete")
    performance_path = _resolve_inside(
        version_root,
        performance_relative,
        label="performance artifact",
        store_root=research_root,
    )
    if performance_path != run_root / "surface" / "performance.parquet":
        raise SingleAssetIntegrityError("selected performance artifact does not belong to the selected run")

    prices_meta = get_parquet_metadata(
        scope="research",
        path=(run_root.relative_to(Path(db_root) / "research") / "prices.parquet").as_posix(),
        db_root=db_root,
    )
    targets_meta = get_parquet_metadata(
        scope="research",
        path=(run_root.relative_to(Path(db_root) / "research") / target_name).as_posix(),
        db_root=db_root,
    )
    price_names = tuple(column.name for column in prices_meta.columns if column.name != "timestamp")
    target_names = tuple(column.name for column in targets_meta.columns if column.name not in {"timestamp", "CASH"})
    if not price_names or set(price_names) != set(target_names):
        raise SingleAssetIntegrityError("selected price and target asset universes do not match")

    benchmark = manifest.get("benchmark")
    benchmark_id = benchmark.get("id") if isinstance(benchmark, dict) else None
    if not isinstance(benchmark_id, str):
        benchmark_id = None
    cost_bps = _finite_number(config.get("trade_cost_bps"), label="trade_cost_bps")
    if cost_bps < 0:
        raise SingleAssetIntegrityError("trade_cost_bps cannot be negative")
    return SelectedLedger(
        strategy_type=strategy_type,
        memory_version=memory_version,
        run_id=run_id,
        experiment=experiment,
        title=str(manifest.get("title") or f"{strategy_type} {memory_version}"),
        benchmark_id=benchmark_id,
        run_root=run_root,
        target_name=target_name,
        returns_name=returns_name,
        performance_path=(performance_path.relative_to(Path(db_root) / "research")).as_posix(),
        asset_names=tuple(sorted(price_names)),
        initial_capital=_finite_number(config.get("initial_capital"), label="initial_capital", positive=True),
        cost_bps=cost_bps,
        rebalance_every_bars=cadence,
    )


# --------------------------------------------------------------------------- #
# Projected reads and accounting
# --------------------------------------------------------------------------- #


def _query(ledger: SelectedLedger, db_root: Path, name: str, columns: tuple[str, ...]) -> pl.DataFrame:
    frame = query_parquet(
        ParquetQuery(
            scope="research",
            path=(ledger.run_root.relative_to(Path(db_root) / "research") / name).as_posix(),
            columns=columns,
            limit=None,
            order_by=columns[0],
        ),
        db_root=db_root,
    ).frame
    if columns[0] == "timestamp":
        frame = frame.with_columns(pl.col("timestamp").dt.convert_time_zone("UTC"))
    return frame


def _validate_series_identity(
    targets: pl.DataFrame,
    prices: pl.DataFrame,
    returns: pl.DataFrame,
    performance: pl.DataFrame,
    *,
    cost_bps: float,
    rebalance_every_bars: int,
) -> None:
    target_times = targets["timestamp"].to_list()
    return_times = returns["timestamp"].to_list()
    price_times = prices["timestamp"].to_list()
    performance_dates = performance["date"].to_list()
    if len(target_times) < 2 or target_times != sorted(set(target_times)):
        raise SingleAssetIntegrityError("selected target timestamps must be unique and ascending")
    if return_times != target_times:
        raise SingleAssetIntegrityError("selected target and return timestamps do not align")
    if price_times != target_times:
        raise SingleAssetIntegrityError("selected prices do not cover the exact ledger timestamps")
    target_dates = [value.astimezone(UTC).date() if isinstance(value, datetime) else value for value in target_times]
    if performance_dates != target_dates:
        raise SingleAssetIntegrityError("selected performance dates do not align with the ledger")

    initial_equity = _finite_number(returns["equity"][0], label="initial equity", positive=True)
    previous_equity = initial_equity
    for index, row in enumerate(returns.iter_rows(named=True)):
        equity = _finite_number(row["equity"], label="saved equity", positive=True)
        price_return = _finite_number(row["price_return"], label="saved price return")
        net_return = _finite_number(row["net_return"], label="saved net return")
        funding_return = _finite_number(row["funding_return"], label="saved funding return")
        cost_return = _finite_number(row["cost_return"], label="saved cost return")
        turnover = _finite_number(row["turnover"], label="saved turnover")
        if cost_return < 0.0 or turnover < 0.0:
            raise SingleAssetIntegrityError("saved cost and turnover cannot be negative")
        if index == 0 and any(
            not math.isclose(value, 0.0, abs_tol=1e-15)
            for value in (price_return, funding_return, cost_return, net_return, turnover)
        ):
            raise SingleAssetIntegrityError("saved ledger must begin with an all-cash zero row")
        if not math.isclose(funding_return, 0.0, abs_tol=1e-15):
            raise SingleAssetIntegrityError("saved funding has no authoritative per-asset attribution")
        if not math.isclose(
            price_return + funding_return - cost_return,
            net_return,
            rel_tol=1e-11,
            abs_tol=1e-13,
        ):
            raise SingleAssetIntegrityError("saved ledger return components do not reconcile")
        if not math.isclose(
            cost_return,
            turnover * cost_bps / 10_000.0,
            rel_tol=1e-11,
            abs_tol=1e-13,
        ):
            raise SingleAssetIntegrityError("saved ledger cost does not match turnover and cost bps")
        if index > 0 and (index - 1) % rebalance_every_bars != 0 and not math.isclose(turnover, 0.0, abs_tol=1e-15):
            raise SingleAssetIntegrityError("saved ledger trades outside its declared cadence")
        if index > 0 and not math.isclose(
            equity / previous_equity - 1.0,
            net_return,
            rel_tol=1e-11,
            abs_tol=1e-13,
        ):
            raise SingleAssetIntegrityError("saved NAV recurrence does not match net return")
        performance_row = performance.row(index, named=True)
        if not math.isclose(
            _finite_number(performance_row["strategy_daily_return"], label="surface return"),
            net_return,
            rel_tol=1e-11,
            abs_tol=1e-13,
        ):
            raise SingleAssetIntegrityError("selected performance does not match the ledger return arm")
        expected_value = equity / initial_equity * 100.0
        if not math.isclose(
            _finite_number(performance_row["strategy_portfolio_value"], label="surface value"),
            expected_value,
            rel_tol=1e-11,
            abs_tol=1e-9,
        ):
            raise SingleAssetIntegrityError("selected performance does not match saved ledger equity")
        previous_equity = equity


def _required_price(value: Any, *, label: str) -> float:
    price = _finite_number(value, label=label, positive=True)
    return price


def _build_asset_frame(
    ledger: SelectedLedger,
    asset: str,
    targets: pl.DataFrame,
    prices: pl.DataFrame,
    returns: pl.DataFrame,
) -> pl.DataFrame:
    timestamps = targets["timestamp"].to_list()
    target_values = targets[asset].to_list()
    price_values = prices[asset].to_list()
    equities = returns["equity"].to_list()
    initial_equity = _finite_number(equities[0], label="initial equity", positive=True)
    if not math.isclose(initial_equity, ledger.initial_capital, rel_tol=1e-12, abs_tol=1e-8):
        raise SingleAssetIntegrityError("saved initial equity does not match selected run config")

    weights = [0.0]
    cumulative = [0.0]
    quantity = 0.0
    cumulative_pnl = 0.0
    for index in range(len(timestamps) - 1):
        target = _finite_number(target_values[index], label=f"{asset} target")
        mark = price_values[index]
        next_mark = price_values[index + 1]
        next_quantity = quantity
        if index % ledger.rebalance_every_bars == 0:
            if target == 0.0:
                next_quantity = 0.0
            else:
                trade_mark = _required_price(mark, label=f"{asset} entry or resize mark")
                equity = _finite_number(equities[index], label="saved pre-trade equity", positive=True)
                next_quantity = target * equity / trade_mark

        traded = next_quantity - quantity
        if traded != 0.0:
            trade_mark = _required_price(mark, label=f"{asset} trade mark")
            fee = abs(traded) * trade_mark * ledger.cost_bps / 10_000.0
        else:
            fee = 0.0
        if next_quantity != 0.0:
            start_mark = _required_price(mark, label=f"{asset} held starting mark")
            ending_mark = _required_price(next_mark, label=f"{asset} held ending mark")
            price_pnl = next_quantity * (ending_mark - start_mark)
        else:
            price_pnl = 0.0
        cumulative_pnl += price_pnl - fee
        cumulative.append(cumulative_pnl / initial_equity * 100.0)

        if next_quantity == 0.0:
            weights.append(0.0)
        else:
            ending_mark = _required_price(next_mark, label=f"{asset} marked held weight")
            ending_equity = _finite_number(equities[index + 1], label="saved ending equity", positive=True)
            weights.append(next_quantity * ending_mark / ending_equity * 100.0)
        quantity = next_quantity

    normalized_prices = [
        None if value is None else _finite_number(value, label=f"{asset} observed price", positive=True)
        for value in price_values
    ]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "price": normalized_prices,
            "weight_percent": weights,
            "cumulative_contribution_pp": cumulative,
        }
    )


def _sample_aligned(frame: pl.DataFrame, *, max_points: int) -> pl.DataFrame:
    if frame.height <= max_points:
        return frame
    prices = frame["price"].to_list()
    required = {0, frame.height - 1}
    for index in range(1, frame.height):
        if (prices[index] is None) != (prices[index - 1] is None):
            required.update((index - 1, index))
    # Display break rows (null contribution) and their neighbours always survive sampling.
    for index in frame.with_row_index().filter(pl.col("cumulative_contribution_pp").is_null())["index"]:
        required.update((index - 1, index, index + 1))
    if len(required) > max_points:
        raise SingleAssetIntegrityError("max_points is too small to preserve every price gap")
    candidates = [index for index in range(frame.height) if index not in required]
    remaining = max_points - len(required)
    if remaining > 0 and candidates:
        step = len(candidates) / remaining
        required.update(candidates[min(math.floor(offset * step), len(candidates) - 1)] for offset in range(remaining))
    return frame[sorted(required)]


# --------------------------------------------------------------------------- #
# Public read model
# --------------------------------------------------------------------------- #


def load_single_asset_view(
    db_root: Path,
    strategy_type: str,
    memory_version: str,
    *,
    asset: str | None = None,
    expected_run_id: str | None = None,
    max_points: int = 2_000,
    config_id: str | None = None,
) -> dict[str, Any]:
    """Return one selected-run asset series or an honest unsupported state."""
    resolved_db_root = Path(db_root).resolve()
    ledger = _load_selected_ledger(
        resolved_db_root,
        strategy_type,
        memory_version,
        expected_run_id=expected_run_id,
    )
    if ledger is None:
        return {
            "available": False,
            "reason": "The selected result has no supported saved ordinary-ledger attribution artifacts.",
            "strategy_type": strategy_type,
            "memory_version": memory_version,
            "run_id": expected_run_id,
            "assets": [],
            "asset": None,
            "data": pl.DataFrame(
                schema={
                    "timestamp": pl.Datetime("us"),
                    "price": pl.Float64,
                    "weight_percent": pl.Float64,
                    "cumulative_contribution_pp": pl.Float64,
                }
            ),
        }

    if isinstance(ledger, SelectedAttribution):
        return _load_attribution_view(resolved_db_root, ledger, asset, config_id, max_points)
    if config_id is not None:
        raise SingleAssetSelectionError("This legacy result has no configuration selector")

    selected_asset = asset
    if selected_asset is None:
        selected_asset = ledger.benchmark_id if ledger.benchmark_id in ledger.asset_names else ledger.asset_names[0]
    if selected_asset == "CASH" or selected_asset not in ledger.asset_names:
        raise SingleAssetSelectionError(f"Asset '{selected_asset}' is not in selected run {ledger.run_id}")

    targets = _query(ledger, resolved_db_root, ledger.target_name, ("timestamp", selected_asset))
    returns = _query(ledger, resolved_db_root, ledger.returns_name, _RETURN_COLUMNS)
    prices = _query(ledger, resolved_db_root, "prices.parquet", ("timestamp", selected_asset))
    prices = prices.join(targets.select("timestamp"), on="timestamp", how="inner", validate="1:1")
    performance = query_parquet(
        ParquetQuery(
            scope="research",
            path=ledger.performance_path,
            columns=_PERFORMANCE_COLUMNS,
            limit=None,
            order_by="date",
        ),
        db_root=resolved_db_root,
    ).frame
    _validate_series_identity(
        targets,
        prices,
        returns,
        performance,
        cost_bps=ledger.cost_bps,
        rebalance_every_bars=ledger.rebalance_every_bars,
    )
    full_frame = _build_asset_frame(ledger, selected_asset, targets, prices, returns)
    display_frame = _sample_aligned(full_frame, max_points=max_points)
    non_null_prices = full_frame.filter(pl.col("price").is_not_null())
    return {
        "available": True,
        "reason": None,
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "run_id": ledger.run_id,
        "experiment": ledger.experiment,
        "title": ledger.title,
        "artifact_contract": "ordinary_ledger_v1",
        "asset": selected_asset,
        "assets": list(ledger.asset_names),
        "cost_bps": ledger.cost_bps,
        "rebalance_every_bars": ledger.rebalance_every_bars,
        "points_total": full_frame.height,
        "points_returned": display_frame.height,
        "downsampled": display_frame.height < full_frame.height,
        "first_observed_at": (non_null_prices["timestamp"][0].isoformat() if non_null_prices.height else None),
        "last_observed_at": (non_null_prices["timestamp"][-1].isoformat() if non_null_prices.height else None),
        "ever_held": bool(full_frame["weight_percent"].abs().max() > 0),
        "peak_abs_weight_percent": float(full_frame["weight_percent"].abs().max()),
        "ending_contribution_pp": float(full_frame["cumulative_contribution_pp"][-1]),
        "methodology": (
            "Weight is the signed held quantity marked before any rebalance at that close. "
            "Cumulative contribution is additive net PnL as percentage points of starting NAV; "
            "entry, resize, reversal and exit fees land at the following mark."
        ),
        "data": display_frame,
    }


def _attribution_ranking(db_root, selected, config_id, names, capital):
    """Summarize every configured asset once, so the page can rank and pick assets."""
    ledger = query_parquet(ParquetQuery(
        scope="research", path=selected.path.relative_to(db_root / "research").as_posix(),
        columns=("config_id", "asset", "quantity", "weight", "price_pnl", "funding_pnl", "fees"),
        entity_column="config_id", entity_values=(config_id,), limit=None,
    ), db_root=db_root).frame
    ranking = ledger.group_by("asset").agg(
        ((pl.col("price_pnl") + pl.col("funding_pnl") - pl.col("fees")).sum() / capital * 100)
        .alias("net_contribution_pp"),
        (pl.col("weight").abs().mean() * 100).alias("mean_abs_weight_percent"),
        (pl.col("weight").abs().max() * 100).alias("peak_abs_weight_percent"),
        ((pl.col("quantity") != 0).mean() * 100).alias("held_percent"),
    ).sort("asset")
    if sorted(ranking["asset"].to_list()) != sorted(names) or any(
        ranking[name].null_count() or not ranking[name].is_finite().all()
        for name in ranking.columns[1:]
    ):
        raise SingleAssetIntegrityError("attribution ranking does not cover the configured assets")
    return ranking.to_dicts()


def _break_missing_days(frame: pl.DataFrame) -> pl.DataFrame:
    """Daily attribution skips dates outside an account's coverage; mark each skip with one null display row.

    The break row (the day after the last observation before a skip) is never a cash flow or a holding:
    every value is null, so charts end the line there instead of bridging the missing interval.
    """
    gap = frame["timestamp"].diff().fill_null(timedelta(days=1)).shift(-1, fill_value=timedelta(days=1)) > timedelta(days=1)
    if not gap.any():
        return frame
    breaks = frame.filter(gap).select(pl.col("timestamp") + timedelta(days=1)).with_columns(
        *[pl.lit(None, dtype=frame.schema[name]).alias(name) for name in frame.columns if name != "timestamp"])
    return pl.concat([frame, breaks.select(frame.columns)]).sort("timestamp")


def _load_attribution_view(db_root, selected, asset, config_id, max_points):
    """Project one asset, then format saved account cash flows on their published capital basis for charts."""
    meta, manifest = selected.metadata, selected.manifest
    configs = meta.get("configurations")
    if not isinstance(configs, list) or not configs or any(
        not isinstance(c, dict) or not isinstance(c.get("id"), str)
        or not isinstance(c.get("label"), str) or not isinstance(c.get("assets"), list)
        or not c["assets"] or any(not isinstance(a, str) or not a or a == "CASH" for a in c["assets"])
        for c in configs
    ):
        raise SingleAssetIntegrityError("invalid attribution configurations")
    ids = [c["id"] for c in configs]
    if len(ids) != len(set(ids)) or meta.get("selected_config_id") not in ids:
        raise SingleAssetIntegrityError("invalid attribution selection")
    chosen = config_id if config_id is not None else meta["selected_config_id"]
    config = next((c for c in configs if c["id"] == chosen), None)
    if config is None:
        raise SingleAssetSelectionError(f"Unknown attribution configuration '{chosen}'")
    names = config["assets"]
    asset = asset if asset is not None else names[0]
    if asset not in names:
        raise SingleAssetSelectionError(f"Asset '{asset}' is outside this configuration")
    capital = _finite_number(meta.get("initial_capital"), label="attribution initial capital", positive=True)
    # A configuration's own fee wins; the global fee is the fallback for producers without one.
    costs_of = {c["id"]: _finite_number(c.get("cost_bps", meta.get("cost_bps")), label="attribution costs") for c in configs}
    if any(cost < 0 for cost in costs_of.values()):
        raise SingleAssetIntegrityError("negative attribution costs")
    costs = costs_of[chosen]
    basis = meta.get("capital_basis", "actual_holdings")
    if basis not in _ATTRIBUTION_BASES:
        raise SingleAssetIntegrityError("unsupported attribution capital basis")
    frame = query_parquet(ParquetQuery(
        scope="research", path=selected.path.relative_to(db_root / "research").as_posix(),
        columns=("timestamp", "config_id", "asset", "price", "quantity", "weight", "price_pnl", "funding_pnl", "fees"),
        entity_column="asset", entity_values=(asset,), limit=None, order_by="timestamp",
    ), db_root=db_root).frame.filter(pl.col("config_id") == chosen)
    if not isinstance(frame.schema["timestamp"], pl.Datetime) or frame.schema["timestamp"].time_zone is None:
        raise SingleAssetIntegrityError("attribution timestamps must be timezone aware")
    frame = frame.with_columns(pl.col("timestamp").dt.convert_time_zone("UTC"))
    if frame.is_empty() or frame["timestamp"].null_count() or frame["timestamp"].is_duplicated().any():
        raise SingleAssetIntegrityError("missing or duplicate attribution observations")
    for name in ("quantity", "weight", "price_pnl", "funding_pnl", "fees"):
        if frame[name].null_count() or not frame[name].is_finite().all():
            raise SingleAssetIntegrityError(f"nonfinite attribution {name}")
    if frame.filter((pl.col("fees") < 0) | (pl.col("price") <= 0) |
                    (~pl.col("price").is_finite().fill_null(True)) |
                    ((pl.col("quantity") != 0) & pl.col("price").is_null()) |
                    ((pl.col("quantity") == 0) & (pl.col("weight") != 0))).height:
        raise SingleAssetIntegrityError("invalid attributed price or holding")
    ranking = _attribution_ranking(db_root, selected, chosen, names, capital)
    full = _break_missing_days(frame.select("timestamp", "price", (pl.col("weight") * 100).alias("weight_percent"),
        ((pl.col("price_pnl") + pl.col("funding_pnl") - pl.col("fees")).cum_sum() / capital * 100)
        .alias("cumulative_contribution_pp")))
    display = _sample_aligned(full, max_points=max_points)
    observed = full.filter(pl.col("price").is_not_null())
    return dict(available=True, reason=None, strategy_type=manifest["strategy_type"],
        memory_version=manifest["memory_version"], run_id=manifest["run_id"],
        experiment=manifest["experiment"], title=manifest["title"], artifact_contract="asset_attribution_v1",
        config_id=chosen, configurations=[dict(id=c["id"], label=c["label"], cost_bps=costs_of[c["id"]]) for c in configs],
        asset=asset, assets=names, cost_bps=costs, rebalance_every_bars=None,
        points_total=full.height, points_returned=display.height, downsampled=display.height < full.height,
        first_observed_at=observed["timestamp"][0].isoformat() if observed.height else None,
        last_observed_at=observed["timestamp"][-1].isoformat() if observed.height else None,
        ever_held=bool(frame["quantity"].abs().max() > 0), peak_abs_weight_percent=float(full["weight_percent"].abs().max()),
        ending_contribution_pp=float(full["cumulative_contribution_pp"][-1]), ranking=ranking, capital_basis=basis,
        methodology=f"{_ATTRIBUTION_BASES[basis]} Net contribution is cumulative price P&L plus signed funding minus fees, as percentage points of starting account NAV. Cash flows are accounted on the original event grid; missing flat-asset prices remain gaps.",
        data=display)


_ATTRIBUTION_BASES = {
    "actual_holdings": "Daily UTC closing actual holdings.",
    "rebased_windows": (
        "Rebased research attribution across independently funded windows: daily UTC closing holdings, with each "
        "later window's quantities, P&L and fees scaled by the configuration's compounded NAV at that window's start, "
        "so cumulative contribution is consistent with the compounded Overview return. This is not one continuously "
        "funded account; nothing is carried across missing periods."
    ),
}
