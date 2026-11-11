"""Validated research-version performance surfaces for API and frontend discovery.

Usage::
    publish_research_surface(db_root, strategy_type="family", memory_version="v003", ...)
    surface = load_research_surface(db_root, "family", "v003")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import contextlib
import json
import math
import os
import re
import tomllib
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import polars as pl
from signal_analysis import selection

from .contracts import validate_identifier, validate_memory_version
from .paths import FAMILIES_ROOT
from .versioned import discover_strategy_versions

ResearchVersionState = Literal["candidate", "rejected"]
ResearchDisplayState = Literal["baseline", "candidate", "rejected"]
PerformanceUnit = Literal["usd", "index"]
MetricDirection = Literal["higher", "lower", "unranked"]

SCHEMA_VERSION = 1
BASELINE_SCHEMA_VERSION = 1
GRID_SCHEMA_VERSION = 1
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PERFORMANCE_COLUMNS = (
    "date",
    "strategy_daily_return",
    "strategy_portfolio_value",
    "benchmark_daily_return",
    "benchmark_portfolio_value",
)
PNL_COLUMNS = ("timestamp", "cumulative_pnl_usd")
PNL_BENCHMARK_COLUMN = "benchmark_cumulative_pnl_usd"
PNL_INTERPRETATIONS = {"backtest", "protocol_stop"}
DISPLAY_FORMATS = {"number", "percent", "money", "text"}
STRATEGY_LIBRARY_ROOT = FAMILIES_ROOT
# AGENTS.md §2 "Run outputs": a run folder holds standard outputs, not policy internals.
# The cap scales with the grid: max(1 GiB, 48 MiB per account), about twice the size of an
# account that saves portfolio diagnostics and asset attribution.
# Ceiling: a grid that publishes attribution saves it twice (per cell and concatenated into
# surface/asset_attribution.parquet). Revisit (API reads per-cell paths) when a grid run nears
# the cap or the next grid version publishes attribution.
MAX_RUN_BYTES = 1 << 30
MAX_ACCOUNT_BYTES = 48 << 20
# Selection statistics on every published grid of >= 2 configurations.
SELECTION_METHOD_VERSION = 2   # 2: Rademacher bound is Procedure 8.2 (adds the N term)
SELECTION_PERIODS_PER_YEAR, SELECTION_DRAWS, SELECTION_SEED, SELECTION_DELTA = 365, 2000, 7, 0.05
SELECTION_PBO_BLOCKS, SELECTION_RC_BLOCK, SELECTION_RAS_BLOCK = 16, 28, 7
SELECTION_SETTINGS = dict(periods_per_year=SELECTION_PERIODS_PER_YEAR, pbo_blocks=SELECTION_PBO_BLOCKS,
                          reality_check_statistic="sharpe", reality_check_block=SELECTION_RC_BLOCK,
                          rademacher_block=SELECTION_RAS_BLOCK, draws=SELECTION_DRAWS, seed=SELECTION_SEED,
                          delta=SELECTION_DELTA)


# --------------------------------------------------------------------------- #
# Display classification
# --------------------------------------------------------------------------- #


def research_display_state(manifest: Mapping[str, Any]) -> ResearchDisplayState:
    """Derive UI state from correctness validity and explicit operator selection."""
    if manifest.get("operator_baseline") is True:
        return "baseline"
    if manifest.get("state") == "rejected":
        return "rejected"
    return "candidate"


# --------------------------------------------------------------------------- #
# Atomic files and validation
# --------------------------------------------------------------------------- #


def _temporary_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = _temporary_path(path)
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
        temporary.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _write_parquet_atomic(path: Path, frame: pl.DataFrame) -> None:
    temporary = _temporary_path(path)
    try:
        frame.write_parquet(temporary, compression="zstd", compression_level=3)
        temporary.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def load_research_baseline(db_root: Path, strategy_type: str) -> dict[str, Any] | None:
    """Load one operator-selected research baseline pointer."""
    validate_identifier(strategy_type, "strategy_type")
    strategy_root = Path(db_root) / "research" / "strategies" / strategy_type
    pointer_path = strategy_root / "baseline.json"
    if not pointer_path.is_file():
        return None

    pointer = json.loads(pointer_path.read_text())
    if not isinstance(pointer, dict) or pointer.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(f"invalid research baseline pointer: {pointer_path}")
    if pointer.get("strategy_type") != strategy_type:
        raise ValueError("research baseline strategy identity does not match its directory")
    memory_version = pointer.get("memory_version")
    if not isinstance(memory_version, str):
        raise ValueError("research baseline pointer is missing memory_version")
    validate_memory_version(memory_version)

    manifest_path = _resolve_inside(
        strategy_root,
        str(pointer.get("selected_manifest") or ""),
        label="baseline.selected_manifest",
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"research baseline manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("strategy_type") != strategy_type
        or manifest.get("memory_version") != memory_version
        or manifest.get("run_id") != pointer.get("selected_run_id")
    ):
        raise ValueError("research baseline pointer does not match its selected manifest")
    return pointer


def select_research_baseline(
    db_root: Path,
    *,
    strategy_type: str,
    memory_version: str,
    selected_at: datetime | None = None,
) -> Path:
    """Select one research surface as the operator's working baseline."""
    validate_identifier(strategy_type, "strategy_type")
    validate_memory_version(memory_version)
    strategy_root = Path(db_root) / "research" / "strategies" / strategy_type
    version_root = strategy_root / memory_version
    surface_pointer_path = version_root / "surface.json"
    if not surface_pointer_path.is_file():
        raise FileNotFoundError(f"research surface pointer not found: {surface_pointer_path}")
    surface_pointer = json.loads(surface_pointer_path.read_text())
    if not isinstance(surface_pointer, dict) or surface_pointer.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid research surface pointer: {surface_pointer_path}")
    if surface_pointer.get("strategy_type") != strategy_type or surface_pointer.get("memory_version") != memory_version:
        raise ValueError("research surface pointer identity does not match the requested baseline")
    manifest_path = _resolve_inside(
        version_root,
        str(surface_pointer.get("selected_manifest") or ""),
        label="selected_manifest",
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"research surface manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("strategy_type") != strategy_type
        or manifest.get("memory_version") != memory_version
        or not isinstance(manifest.get("run_id"), str)
    ):
        raise ValueError("research surface manifest cannot be selected as a baseline")

    pointer = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "selected_run_id": manifest["run_id"],
        "selected_manifest": manifest_path.relative_to(strategy_root).as_posix(),
        "selected_at": (selected_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
    }
    pointer_path = strategy_root / "baseline.json"
    _write_json_atomic(pointer_path, pointer)
    return pointer_path


def _check_run_size(run_root: Path, configs: int) -> None:
    """Refuse a run folder over max(MAX_RUN_BYTES, MAX_ACCOUNT_BYTES × configs) (AGENTS.md §2 "Run outputs")."""
    limit = max(MAX_RUN_BYTES, MAX_ACCOUNT_BYTES * configs)
    size = sum(path.stat().st_size for path in run_root.rglob("*") if path.is_file()) if run_root.is_dir() else 0
    if size > limit:
        raise ValueError(
            f"research run is {size / 1e9:.2f} GB, over the {limit / 1e9:.2f} GB limit for {configs} "
            f"account(s): {run_root}. Save standard outputs only; rebuild policy internals with the version's rerun.py"
        )


def _resolve_inside(root: Path, relative_path: str, *, label: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise ValueError(f"{label} must be a non-empty relative path")
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes its version directory") from error
    return target


def validate_asset_attribution(frame: pl.DataFrame, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Validate daily holdings and additive account-currency cash flows on their declared capital basis."""
    columns = {"timestamp", "config_id", "asset", "price", "quantity", "weight", "price_pnl", "funding_pnl", "fees"}
    if set(frame.columns) != columns or frame.is_empty():
        raise ValueError("attribution requires the complete daily holdings/cash-flow schema")
    if not isinstance(frame.schema["timestamp"], pl.Datetime) or frame.schema["timestamp"].time_zone != "UTC":
        raise ValueError("attribution timestamps must be UTC datetimes")
    if any(frame[name].null_count() for name in columns - {"price"}):
        raise ValueError("only unheld attribution prices may be null")
    if (frame["timestamp"] != frame["timestamp"].dt.truncate("1d")).any():
        raise ValueError("attribution timestamps must label UTC dates")
    if frame.select(pl.struct("timestamp", "config_id", "asset").is_duplicated().any()).item():
        raise ValueError("duplicate attribution date/configuration/asset")
    for name in columns - {"timestamp", "config_id", "asset"}:
        if not frame[name].is_finite().fill_null(name == "price").all():
            raise ValueError(f"nonfinite attribution {name}")
    if frame.filter((pl.col("price") <= 0) | (pl.col("fees") < 0) |
                    ((pl.col("quantity") != 0) & pl.col("price").is_null()) |
                    ((pl.col("quantity") == 0) & (pl.col("weight") != 0))).height:
        raise ValueError("invalid attribution price, fee or flat holding")

    def valid_amount(value: Any) -> bool:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0

    for name in ("initial_capital", "cost_bps"):
        if not valid_amount(metadata.get(name)):
            raise ValueError(f"invalid attribution {name}")
    if metadata["initial_capital"] == 0:
        raise ValueError("attribution initial_capital must be positive")
    configs = metadata.get("configurations")
    if not isinstance(configs, list) or not configs or any(
        not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]
        or not isinstance(row.get("label"), str) or not row["label"] for row in configs
    ):
        raise ValueError("attribution configurations require ids and labels")
    # A configuration's own cost_bps overrides the global fee, which stays the fallback for the others.
    if any("cost_bps" in row and not valid_amount(row["cost_bps"]) for row in configs):
        raise ValueError("invalid attribution configuration cost_bps")
    ids = [row["id"] for row in configs]
    if len(ids) != len(set(ids)) or set(ids) != set(frame["config_id"].unique()) or metadata.get("selected_config_id") not in ids:
        raise ValueError("attribution configuration identity mismatch")
    if frame.filter((pl.col("asset") == "") | (pl.col("asset") == "CASH")).height:
        raise ValueError("attribution requires risky asset identifiers")
    # Optional reporting basis: absent means actual saved holdings; "rebased_windows" means each later
    # independently funded window's quantities and cash flows are scaled to the compounded NAV at its start.
    if metadata.get("capital_basis", "actual_holdings") not in ("actual_holdings", "rebased_windows"):
        raise ValueError("invalid attribution capital_basis")
    return dict(contract="asset_attribution_v1", initial_capital=metadata["initial_capital"],
                **({"capital_basis": metadata["capital_basis"]} if "capital_basis" in metadata else {}),
                cost_bps=metadata["cost_bps"], selected_config_id=metadata["selected_config_id"],
                configurations=[dict(id=row["id"], label=row["label"], assets=sorted(
                    frame.filter(pl.col("config_id") == row["id"])["asset"].unique().to_list()),
                    **({"cost_bps": row["cost_bps"]} if "cost_bps" in row else {})) for row in configs],
                row_count=frame.height, columns=frame.columns)


def validate_performance_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Validate and normalize one research performance surface."""
    missing = [column for column in PERFORMANCE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"performance surface missing columns: {missing}")
    if frame.is_empty():
        raise ValueError("performance surface cannot be empty")

    normalized = frame.with_columns(
        pl.col("date").cast(pl.Date, strict=True),
        *[pl.col(column).cast(pl.Float64, strict=True) for column in PERFORMANCE_COLUMNS if column != "date"],
    )
    dates = normalized["date"]
    if dates.null_count() or dates.n_unique() != normalized.height or not dates.is_sorted():
        raise ValueError("performance dates must be non-null, unique, and ascending")

    for column in PERFORMANCE_COLUMNS[1:]:
        values = normalized[column].to_list()
        if any(value is None or not math.isfinite(value) for value in values):
            raise ValueError(f"performance column '{column}' must contain only finite values")
    for column in ("strategy_daily_return", "benchmark_daily_return"):
        minimum = normalized[column].min()
        if not isinstance(minimum, (int, float)):
            raise ValueError(f"performance column '{column}' has no numeric minimum")
        if minimum <= -1.0:
            raise ValueError(f"performance column '{column}' contains a return at or below -100%")

    for prefix in ("strategy", "benchmark"):
        expected = 100.0
        for daily_return, portfolio_value in normalized.select(
            f"{prefix}_daily_return", f"{prefix}_portfolio_value"
        ).iter_rows():
            expected *= 1.0 + daily_return
            if not math.isclose(expected, portfolio_value, rel_tol=1e-10, abs_tol=1e-8):
                raise ValueError(f"{prefix} portfolio values do not reconcile with daily returns")
    return normalized


def validate_pnl_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Validate one cumulative-PnL chart artifact."""
    missing = [column for column in PNL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"PnL surface missing columns: {missing}")
    if frame.is_empty():
        raise ValueError("PnL surface cannot be empty")

    value_columns = ["cumulative_pnl_usd"]
    if PNL_BENCHMARK_COLUMN in frame.columns:
        value_columns.append(PNL_BENCHMARK_COLUMN)
    selected_columns = [*PNL_COLUMNS, *value_columns[1:]]
    normalized = frame.select(selected_columns).with_columns(
        pl.col("timestamp").cast(pl.Datetime("ms", time_zone="UTC"), strict=True),
        *[pl.col(column).cast(pl.Float64, strict=True) for column in value_columns],
    )
    timestamps = normalized["timestamp"]
    if timestamps.null_count() or timestamps.n_unique() != normalized.height or not timestamps.is_sorted():
        raise ValueError("PnL timestamps must be non-null, unique, and ascending")
    for column in value_columns:
        values = normalized[column].to_list()
        if any(value is None or not math.isfinite(value) for value in values):
            raise ValueError("PnL values must be finite")
        if values[0] != 0.0:
            raise ValueError("PnL surface must start at exactly zero")
    return normalized


def _validate_pnl_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the chart interpretation and fixed allocation contract."""
    label = metadata.get("label")
    allocation = metadata.get("allocation_usd")
    interpretation = metadata.get("interpretation")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("PnL metadata requires a non-empty label")
    if (
        not isinstance(allocation, (int, float))
        or isinstance(allocation, bool)
        or not math.isfinite(allocation)
        or allocation <= 0.0
    ):
        raise ValueError("PnL metadata requires a positive finite allocation_usd")
    if interpretation not in PNL_INTERPRETATIONS:
        raise ValueError("PnL metadata has an invalid interpretation")
    return {
        "label": label,
        "allocation_usd": float(allocation),
        "interpretation": interpretation,
    }


def _validate_display_collections(
    diagnostics: Sequence[Mapping[str, Any]],
    gates: Sequence[Mapping[str, Any]],
) -> None:
    """Require the shared frontend display contract before publication or loading."""
    for diagnostic in diagnostics:
        if (
            not all(isinstance(diagnostic.get(key), str) and diagnostic[key] for key in ("key", "label"))
            or diagnostic.get("format") not in DISPLAY_FORMATS
            or not isinstance(diagnostic.get("value"), (int, float, str))
            or isinstance(diagnostic.get("value"), bool)
        ):
            raise ValueError("research surface diagnostic has invalid display metadata")
        value = diagnostic["value"]
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError("research surface diagnostic value must be finite")

    for gate in gates:
        result = gate.get("result")
        if (
            not all(isinstance(gate.get(key), str) and gate[key] for key in ("name", "requirement"))
            or gate.get("format") not in DISPLAY_FORMATS
            or not isinstance(gate.get("passed"), bool)
            or (result is not None and not isinstance(result, (int, float, str)))
            or isinstance(result, bool)
        ):
            raise ValueError("research surface gate has invalid display metadata")
        if isinstance(result, (int, float)) and not math.isfinite(result):
            raise ValueError("research surface gate result must be finite")


def validate_grid_summary(frame: pl.DataFrame, grid: Mapping[str, Any]) -> pl.DataFrame:
    """Validate one optimizer-grid summary against its declared display contract."""
    if grid.get("grid_schema_version") != GRID_SCHEMA_VERSION:
        raise ValueError("research grid has an unsupported schema version")
    dimensions = grid.get("dimensions")
    metrics = grid.get("metrics")
    if not isinstance(dimensions, list) or len(dimensions) < 2:
        raise ValueError("research grid requires at least two dimensions")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("research grid requires at least one metric")

    dimension_keys = [item.get("key") for item in dimensions if isinstance(item, dict)]
    metric_keys = [item.get("key") for item in metrics if isinstance(item, dict)]
    if (
        len(dimension_keys) != len(dimensions)
        or len(set(dimension_keys)) != len(dimension_keys)
        or not all(isinstance(key, str) and key for key in dimension_keys)
    ):
        raise ValueError("research grid dimensions require unique non-empty keys")
    if (
        len(metric_keys) != len(metrics)
        or len(set(metric_keys)) != len(metric_keys)
        or not all(isinstance(key, str) and key for key in metric_keys)
    ):
        raise ValueError("research grid metrics require unique non-empty keys")

    required = ["rank", "config_id", "is_selected", "is_control", *dimension_keys, *metric_keys]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"research grid summary missing columns: {missing}")
    if frame.is_empty():
        raise ValueError("research grid summary cannot be empty")

    normalized = frame.select(required).sort("rank")
    ranks = normalized["rank"].cast(pl.Int64, strict=True)
    expected_ranks = pl.Series("rank", range(1, normalized.height + 1), dtype=pl.Int64)
    if not ranks.equals(expected_ranks):
        raise ValueError("research grid ranks must be unique and contiguous from one")
    config_ids = normalized["config_id"].cast(pl.String, strict=True)
    if config_ids.null_count() or config_ids.n_unique() != normalized.height:
        raise ValueError("research grid config_id values must be non-null and unique")

    selected_id = grid.get("selected_config_id")
    control_id = grid.get("control_config_id")
    known_config_ids = set(config_ids.to_list())
    if (
        not isinstance(selected_id, str)
        or not isinstance(control_id, str)
        or selected_id not in known_config_ids
        or control_id not in known_config_ids
    ):
        raise ValueError("research grid selected and control configurations must exist")
    selected = normalized["is_selected"].cast(pl.Boolean, strict=True)
    control = normalized["is_control"].cast(pl.Boolean, strict=True)
    if selected.sum() != 1 or control.sum() != 1:
        raise ValueError("research grid requires exactly one selected and one control row")
    if normalized.filter(selected)["config_id"].item() != selected_id:
        raise ValueError("research grid selected flag does not match selected_config_id")
    if normalized.filter(control)["config_id"].item() != control_id:
        raise ValueError("research grid control flag does not match control_config_id")

    for item in dimensions:
        key = item["key"]
        values = item.get("values")
        if not isinstance(item.get("label"), str) or not isinstance(item.get("format"), str):
            raise ValueError(f"research grid dimension '{key}' requires label and format")
        if not isinstance(values, list) or not values:
            raise ValueError(f"research grid dimension '{key}' requires declared values")
        actual = normalized[key].unique().sort().to_list()
        if actual != sorted(values):
            raise ValueError(f"research grid dimension '{key}' values do not match the summary")
    for item in metrics:
        key = item["key"]
        if (
            not isinstance(item.get("label"), str)
            or item.get("format") not in {"number", "percent"}
            or not isinstance(item.get("higher_is_better"), bool)
        ):
            raise ValueError(f"research grid metric '{key}' has invalid display metadata")
        values = normalized[key].cast(pl.Float64, strict=True).to_list()
        nullable = item.get("nullable", False)
        if not isinstance(nullable, bool):
            raise ValueError(f"research grid metric '{key}' nullable must be boolean")
        if any((not nullable) if value is None else not math.isfinite(value) for value in values):
            raise ValueError(f"research grid metric '{key}' must contain only finite values")
    return normalized.with_columns(
        pl.col("rank").cast(pl.Int64),
        pl.col("config_id").cast(pl.String),
        pl.col("is_selected").cast(pl.Boolean),
        pl.col("is_control").cast(pl.Boolean),
    )


def _validate_grid_series(version_root: Path, grid: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    series = grid.get("series")
    if not isinstance(series, dict):
        raise ValueError("research grid requires series metadata")
    required = ("path", "config_id_column", "date_column", "return_column")
    if any(not isinstance(series.get(key), str) or not series[key] for key in required):
        raise ValueError("research grid series metadata is incomplete")
    path = _resolve_inside(version_root, series["path"], label="grid.series.path")
    if not path.is_file():
        raise FileNotFoundError(f"research grid series not found: {path}")
    schema = pl.read_parquet_schema(path)
    missing = [series[key] for key in required[1:] if series[key] not in schema]
    if missing:
        raise ValueError(f"research grid series missing columns: {missing}")
    return path, series


# --------------------------------------------------------------------------- #
# Selection statistics
# --------------------------------------------------------------------------- #


def _grid_returns(
    series_path: Path, series: Mapping[str, Any], config_ids: Sequence[str]
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Read grid series into a dates × configs matrix in ``config_ids`` order, oldest row first."""
    config, date, value = (series[key] for key in ("config_id_column", "date_column", "return_column"))
    frame = (
        pl.read_parquet(series_path, columns=[config, date, value])
        .select(pl.col(config).cast(pl.String).alias("config_id"), pl.col(date).alias("date"),
                pl.col(value).cast(pl.Float64).alias("value"))
        .pivot(on="config_id", index="date", values="value")
        .sort("date")
    )
    matrix = frame.select(config_ids).to_numpy()
    scope: dict[str, Any] = {"rows": frame.height, "dropped_leading_zero_row": False}
    if not np.isfinite(matrix).all():
        return None, {**scope, "reason": "grid series configurations do not share one finite date calendar"}
    if matrix.shape[0] and (matrix[0] == 0.0).all():
        matrix = matrix[1:]
        scope["dropped_leading_zero_row"] = True
    first, last = frame["date"][int(scope["dropped_leading_zero_row"])], frame["date"][-1]
    return matrix, {**scope, "rows": matrix.shape[0], "start": str(first), "end": str(last)}


def _family_trial_count(db_root: Path, strategy_type: str, memory_version: str, configs: int) -> int:
    """This grid plus every other version's published grid (lower bound on the family's trials)."""
    total = configs
    for pointer in sorted((Path(db_root) / "research" / "strategies" / strategy_type).glob("v*/surface.json")):
        if pointer.parent.name == memory_version:
            continue
        try:
            loaded = load_research_surface(db_root, strategy_type, pointer.parent.name)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pl.exceptions.PolarsError):
            continue
        grid = loaded[1].get("grid") if loaded is not None else None
        if isinstance(grid, dict) and isinstance(grid.get("summary"), dict):
            total += int(grid["summary"].get("row_count") or 0)
    return total


def _selection_diagnostics(selection_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Up to ten display rows; an unavailable statistic shows its reason as text."""
    stats = selection_record["statistics"]
    n_raw = selection_record["configs"]
    family = selection_record["family_size"]

    def row(key: str, label: str, result: Mapping[str, Any], value: Any, fmt: str = "number") -> dict[str, Any]:
        if not result.get("available"):
            return dict(key=key, label=label, value=f"unavailable: {result.get('reason')}", format="text")
        return dict(key=key, label=label, value=value, format=fmt)

    psr, dsr_raw, dsr_eff = stats["psr"], stats["dsr_raw"], stats["dsr_effective"]
    pbo, rc, ras = stats["pbo"], stats["reality_check"], stats["rademacher"]
    n_eff = stats["effective_trials"].get("effective_trials")
    ras_target = (ras.get("selected") or ras.get("best") or {}) if ras.get("available") else {}
    return [
        row("selection_psr", "Selected PSR (SR > 0)", psr, psr.get("psr")),
        row("selection_dsr_raw", f"DSR (N = {n_raw} raw)", dsr_raw, dsr_raw.get("dsr")),
        row("selection_dsr_effective",
            f"DSR (N eff = {n_eff:.1f})" if n_eff is not None else "DSR (N eff)", dsr_eff, dsr_eff.get("dsr")),
        row("selection_pbo", f"PBO (CSCV, {SELECTION_PBO_BLOCKS} blocks)", pbo, pbo.get("pbo")),
        row("selection_reality_check", "Reality check p vs control (raw / studentized)", rc,
            f"{rc.get('raw_p', 0):.3f} / {rc.get('studentized_p', 0):.3f}", "text"),
        row("selection_holm", "Holm survivors vs control (5%)", rc,
            f"{rc.get('holm_survivors')} of {family}", "text"),
        row("selection_rademacher",
            f"Rademacher bound on {'selected' if ras.get('selected') else 'best'} Sharpe (annualized)",
            ras, ras_target.get("bound_annualized")),
        dict(key="selection_family_trials",
             label="Family trials (lower bound: unpublished and pre-grid trials are not counted)",
             value=selection_record["family_trial_count"], format="number"),
    ]


def _selection_statistics(
    db_root: Path,
    strategy_type: str,
    memory_version: str,
    normalized_grid: pl.DataFrame,
    grid: Mapping[str, Any],
    series_path: Path,
    series: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Measure the displayed winner's selection inflation over a grid of >= 2 configurations.

    PSR, DSR and PBO use every grid configuration; the reality check and Rademacher bound
    use the family (every configuration except the control) against the control, which is
    never chosen by performance. Display only: nothing here selects or gates.
    """
    config_ids = normalized_grid["config_id"].to_list()
    if len(config_ids) < 2:
        return None
    selected_id, control_id = grid["selected_config_id"], grid["control_config_id"]
    family_ids = [config_id for config_id in config_ids if config_id != control_id]
    record: dict[str, Any] = {
        "method_version": SELECTION_METHOD_VERSION,
        "settings": dict(SELECTION_SETTINGS),
        "selected_config_id": selected_id,
        "base_config_id": control_id,
        "configs": len(config_ids),
        "family_size": len(family_ids),
        "family_trial_count": _family_trial_count(db_root, strategy_type, memory_version, len(config_ids)),
        "family_trial_count_note": "lower bound: unpublished and pre-grid trials are not counted",
    }
    matrix, scope = _grid_returns(series_path, series, config_ids)
    record["sample"] = scope
    if matrix is None:
        unavailable = {"available": False, "reason": scope["reason"]}
        record["statistics"] = {key: unavailable for key in (
            "psr", "effective_trials", "dsr_raw", "dsr_effective", "pbo", "reality_check", "rademacher")}
        return record
    chosen = config_ids.index(selected_id)
    family = matrix[:, [config_ids.index(config_id) for config_id in family_ids]]
    control = matrix[:, [config_ids.index(control_id)] * len(family_ids)]
    effective = selection.effective_trials(matrix)
    record["statistics"] = {
        "psr": selection.probabilistic_sharpe(matrix[:, chosen]),
        "effective_trials": effective,
        "dsr_raw": selection.deflated_sharpe(matrix, chosen),
        "dsr_effective": (selection.deflated_sharpe(matrix, chosen, trials=effective["effective_trials"])
                          if effective["available"] else effective),
        "pbo": selection.pbo_cscv(matrix, blocks=SELECTION_PBO_BLOCKS),
        "reality_check": selection.reality_check(
            family, control, statistic="sharpe", block=SELECTION_RC_BLOCK, draws=SELECTION_DRAWS,
            seed=SELECTION_SEED, periods_per_year=SELECTION_PERIODS_PER_YEAR, names=family_ids),
        "rademacher": selection.rademacher_bound(
            family, block=SELECTION_RAS_BLOCK, draws=SELECTION_DRAWS, seed=SELECTION_SEED, delta=SELECTION_DELTA,
            periods_per_year=SELECTION_PERIODS_PER_YEAR, names=family_ids,
            selected=family_ids.index(selected_id) if selected_id in family_ids else None),
    }
    return record


# --------------------------------------------------------------------------- #
# Metrics and publication
# --------------------------------------------------------------------------- #


def summarize_returns(returns: Sequence[float], periods_per_year: float = 365.0) -> dict[str, float | None]:
    """Return the standard performance metrics for one daily series, annualized at ``periods_per_year``."""
    if not returns:
        raise ValueError("cannot summarize an empty return series")
    count = len(returns)
    wealth = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        if not math.isfinite(value) or value < -1.0:
            raise ValueError("returns must be finite and at least -100%")
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, wealth / peak - 1.0)

    mean = sum(returns) / count
    variance = sum((value - mean) ** 2 for value in returns) / count
    standard_deviation = math.sqrt(variance)
    annualized_return = wealth ** (periods_per_year / count) - 1.0 if wealth > 0.0 else None
    return {
        "total_return": wealth - 1.0,
        "sharpe": mean / standard_deviation * math.sqrt(periods_per_year) if standard_deviation > 0.0 else None,
        "max_drawdown": max_drawdown,
        "ending_value": wealth * 100.0,
        "annualized_return": annualized_return,
        "annualized_volatility": standard_deviation * math.sqrt(periods_per_year),
        "calmar": (
            annualized_return / abs(max_drawdown) if annualized_return is not None and max_drawdown < 0.0 else None
        ),
        "positive_days": sum(value > 0.0 for value in returns) / count,
    }


# Canonical comparable metrics: key -> (direction, existing aliases). Signed
# max_drawdown is higher-is-better (closer to zero). Every other key, including
# exposure, activity, dollar and diagnostic fields, is unranked whatever its saved
# higher_is_better boolean says; sealed manifests keep their booleans untouched.
RANKED_METRICS: dict[str, tuple[MetricDirection, tuple[str, ...]]] = {
    "total_return": ("higher", ()),
    "annualized_return": ("higher", ("cagr",)),
    "ending_value": ("higher", ()),
    "positive_days": ("higher", ()),
    "sortino": ("higher", ()),
    "sharpe": ("higher", ("sharpe_365",)),
    "calmar": ("higher", ()),
    "martin": ("higher", ()),
    "max_drawdown": ("higher", ("maximum_drawdown",)),
    "annualized_volatility": ("lower", ("volatility_365",)),
    "longest_drawdown_days": ("lower", ()),
    "current_drawdown_days": ("lower", ()),
}
_METRIC_ALIASES = {alias: key for key, (_, aliases) in RANKED_METRICS.items() for alias in aliases}


def canonical_metric(key: str) -> tuple[str, MetricDirection]:
    """Resolve a saved metric key or alias to its canonical key and direction."""
    canonical = _METRIC_ALIASES.get(key, key)
    if canonical in RANKED_METRICS:
        return canonical, RANKED_METRICS[canonical][0]
    return key, "unranked"


def metric_definitions() -> list[dict[str, Any]]:
    """Emit the canonical ranked metric table for API consumers."""
    return [
        {"key": key, "aliases": list(aliases), "direction": direction}
        for key, (direction, aliases) in RANKED_METRICS.items()
    ]


def validate_performance_metrics(metrics: Mapping[str, Any]) -> None:
    """Require the headline metric contract consumed by the research UI.

    Overrides retain their own statistical conventions and may include additional
    research fields, but must supply every display field explicitly. An additional
    numeric field must be finite or null.
    """
    required = {
        "total_return", "sharpe", "max_drawdown", "ending_value",
        "annualized_return", "annualized_volatility", "calmar", "positive_days",
    }
    nullable = {"sharpe", "annualized_return", "calmar"}
    if set(metrics) != {"strategy", "benchmark"}:
        raise ValueError("metrics must contain exactly strategy and benchmark")
    for role in ("strategy", "benchmark"):
        values = metrics[role]
        if not isinstance(values, Mapping):
            raise ValueError(f"metrics.{role} must be an object")
        missing = required - values.keys()
        if missing:
            raise ValueError(f"metrics.{role} missing display fields: {', '.join(sorted(missing))}")
        extra_numeric = {
            key for key in values.keys() - required
            if isinstance(values[key], (int, float)) and not isinstance(values[key], bool)
        }
        for key in required | extra_numeric:
            value = values[key]
            if value is None and key in nullable:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"metrics.{role}.{key} must be a finite number" +
                                 (" or null" if key in nullable else ""))


def publish_research_surface(
    db_root: Path,
    *,
    strategy_type: str,
    memory_version: str,
    state: ResearchVersionState,
    experiment: str,
    run_id: str,
    title: str,
    summary: str,
    performance: pl.DataFrame | None = None,
    performance_unit: PerformanceUnit = "usd",
    pnl: pl.DataFrame | None = None,
    pnl_metadata: Mapping[str, Any] | None = None,
    benchmark: Mapping[str, str] | None = None,
    diagnostics: Sequence[Mapping[str, Any]] = (),
    gates: Sequence[Mapping[str, Any]] = (),
    disclosures: Sequence[str] = (),
    provenance: Sequence[Mapping[str, str]] = (),
    metrics_override: Mapping[str, Mapping[str, float | None]] | None = None,
    grid_summary: pl.DataFrame | None = None,
    grid: Mapping[str, Any] | None = None,
    published_at: datetime | None = None,
    asset_attribution: pl.DataFrame | None = None,
    attribution_metadata: Mapping[str, Any] | None = None,
) -> Path:
    """Publish one immutable performance, PnL, or text-only research record.

    ``provenance`` items are ``{"label", "path"}`` mappings; a ``label`` that an installed DB API
    extension registered as a surface supplement makes the API load that artifact for display.
    """
    validate_identifier(strategy_type, "strategy_type")
    if (asset_attribution is None) != (attribution_metadata is None):
        raise ValueError("asset_attribution and attribution_metadata must be supplied together")
    attribution_manifest = None
    if asset_attribution is not None and attribution_metadata is not None:
        attribution_manifest = validate_asset_attribution(asset_attribution, attribution_metadata)
    validate_memory_version(memory_version)
    validate_identifier(experiment, "experiment")
    if not _SAFE_SLUG.fullmatch(run_id):
        raise ValueError("run_id must be a filesystem-safe slug")
    if state not in {"candidate", "rejected"}:
        raise ValueError("research surface state must be 'candidate' or 'rejected'")
    if not title.strip() or not summary.strip():
        raise ValueError("research surface title and summary are required")
    if (grid_summary is None) != (grid is None):
        raise ValueError("grid_summary and grid must be supplied together")
    if (pnl is None) != (pnl_metadata is None):
        raise ValueError("pnl and pnl_metadata must be supplied together")
    if performance is not None and pnl is not None:
        raise ValueError("research surfaces cannot combine performance and PnL artifacts")
    if performance_unit not in {"usd", "index"}:
        raise ValueError("performance_unit must be 'usd' or 'index'")
    if performance is None and performance_unit != "usd":
        raise ValueError("performance_unit applies only to performance surfaces")
    _validate_display_collections(diagnostics, gates)
    if any(str(item.get("key", "")).startswith("selection_") for item in diagnostics):
        raise ValueError("diagnostic keys starting with 'selection_' are reserved for selection statistics")
    normalized = validate_performance_frame(performance) if performance is not None else None
    normalized_pnl = validate_pnl_frame(pnl) if pnl is not None else None
    validated_pnl_metadata = _validate_pnl_metadata(pnl_metadata) if pnl_metadata is not None else None
    if performance is None:
        if metrics_override is not None or grid is not None:
            raise ValueError("text-only research records cannot include performance metadata")
        if benchmark is not None and (not benchmark.get("id") or not benchmark.get("label")):
            raise ValueError("PnL benchmark requires a non-empty id and label")
        has_pnl_benchmark = normalized_pnl is not None and PNL_BENCHMARK_COLUMN in normalized_pnl.columns
        if normalized_pnl is None and benchmark is not None:
            raise ValueError("text-only research records cannot include performance metadata")
        if normalized_pnl is not None and has_pnl_benchmark != (benchmark is not None):
            raise ValueError("PnL benchmark metadata and column must be supplied together")
    elif benchmark is None or not benchmark.get("id") or not benchmark.get("label"):
        raise ValueError("performance surfaces require a non-empty benchmark id and label")
    if metrics_override is not None:
        # Reject invalid overrides before creating artifacts or moving the pointer.
        validate_performance_metrics(metrics_override)
    version_root = Path(db_root) / "research" / "strategies" / strategy_type / memory_version
    run_root = version_root / experiment / run_id
    surface_root = run_root / "surface"
    performance_path = surface_root / "performance.parquet"
    pnl_path = surface_root / "pnl.parquet"
    manifest_path = surface_root / "manifest.json"
    if performance_path.exists() or pnl_path.exists() or manifest_path.exists():
        raise FileExistsError(f"immutable research surface already exists: {surface_root}")

    normalized_grid: pl.DataFrame | None = None
    grid_manifest: dict[str, Any] | None = None
    selection_record: dict[str, Any] | None = None
    if grid_summary is not None and grid is not None:
        normalized_grid = validate_grid_summary(grid_summary, grid)
        series_path, series = _validate_grid_series(version_root, grid)
        series_stats = cast(
            pl.DataFrame,
            pl.scan_parquet(series_path)
            .group_by(pl.col(series["config_id_column"]).cast(pl.String).alias("config_id"))
            .agg(
                pl.len().alias("rows"),
                pl.col(series["date_column"]).n_unique().alias("unique_dates"),
            )
            .collect(),
        )
        series_config_ids = series_stats["config_id"].sort().to_list()
        summary_config_ids = normalized_grid["config_id"].sort().to_list()
        if series_config_ids != summary_config_ids:
            raise ValueError("research grid series configurations do not match the summary")
        if series_stats.filter(pl.col("rows") != pl.col("unique_dates")).height or series_stats["rows"].n_unique() != 1:
            raise ValueError("research grid series must contain one complete unique-date path per configuration")
        grid_manifest = {
            "grid_schema_version": GRID_SCHEMA_VERSION,
            "dimensions": [dict(item) for item in grid["dimensions"]],
            "metrics": [dict(item) for item in grid["metrics"]],
            "selected_config_id": grid["selected_config_id"],
            "control_config_id": grid["control_config_id"],
            "series": {
                **{key: series[key] for key in ("path", "config_id_column", "date_column", "return_column")},
                "row_count": cast(
                    pl.DataFrame,
                    pl.scan_parquet(series_path).select(pl.len()).collect(),
                ).item(),
            },
        }
        _check_run_size(run_root, normalized_grid.height)
        selection_record = _selection_statistics(
            Path(db_root), strategy_type, memory_version, normalized_grid, grid, series_path, series
        )
    else:
        _check_run_size(run_root, 1)
    display_diagnostics = [dict(item) for item in diagnostics]
    if selection_record is not None:
        display_diagnostics += _selection_diagnostics(selection_record)
        _validate_display_collections(display_diagnostics, ())

    if normalized is not None:
        _write_parquet_atomic(performance_path, normalized)
    if normalized_pnl is not None:
        _write_parquet_atomic(pnl_path, normalized_pnl)
    if normalized_grid is not None and grid_manifest is not None:
        grid_summary_path = surface_root / "grid_summary.parquet"
        _write_parquet_atomic(grid_summary_path, normalized_grid)
        grid_manifest["summary"] = {
            "path": grid_summary_path.relative_to(version_root).as_posix(),
            "columns": normalized_grid.columns,
            "row_count": normalized_grid.height,
        }
    timestamp = (published_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    if normalized is None:
        performance_manifest = None
        metrics = None
    elif metrics_override is None:
        performance_manifest = {
            "path": performance_path.relative_to(version_root).as_posix(),
            "columns": normalized.columns,
            "row_count": normalized.height,
        }
        metrics = {
            "strategy": summarize_returns(normalized["strategy_daily_return"].to_list()),
            "benchmark": summarize_returns(normalized["benchmark_daily_return"].to_list()),
        }
    else:
        performance_manifest = {
            "path": performance_path.relative_to(version_root).as_posix(),
            "columns": normalized.columns,
            "row_count": normalized.height,
        }
        metrics = {name: dict(metrics_override[name]) for name in ("strategy", "benchmark")}
    pnl_manifest = None
    if normalized_pnl is not None and validated_pnl_metadata is not None:
        pnl_manifest = {
            "path": pnl_path.relative_to(version_root).as_posix(),
            "columns": normalized_pnl.columns,
            "row_count": normalized_pnl.height,
            **validated_pnl_metadata,
        }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "state": state,
        "experiment": experiment,
        "run_id": run_id,
        "published_at": timestamp,
        "title": title,
        "summary": summary,
        "benchmark": dict(benchmark) if benchmark is not None else None,
        "performance": performance_manifest,
        "performance_unit": performance_unit if performance_manifest is not None else None,
        "pnl": pnl_manifest,
        "metrics": metrics,
        "diagnostics": display_diagnostics,
        "gates": [dict(item) for item in gates],
        "disclosures": list(disclosures),
        "provenance": [dict(item) for item in provenance],
    }
    if grid_manifest is not None:
        manifest["grid"] = grid_manifest
    if selection_record is not None:
        manifest["selection"] = selection_record
    if asset_attribution is not None and attribution_manifest is not None:
        attribution_path = surface_root / "asset_attribution.parquet"
        # Asset-major order compresses the panel ~25% and lets single-asset reads skip row groups.
        _write_parquet_atomic(attribution_path, asset_attribution.sort("asset", "config_id", "timestamp"))
        manifest["attribution"] = {
            **attribution_manifest, "path": attribution_path.relative_to(version_root).as_posix(),
        }
    _write_json_atomic(manifest_path, manifest)

    pointer = {
        "schema_version": SCHEMA_VERSION,
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "state": state,
        "selected_manifest": manifest_path.relative_to(version_root).as_posix(),
        "published_at": timestamp,
    }
    pointer_path = version_root / "surface.json"
    _write_json_atomic(pointer_path, pointer)
    return pointer_path


# --------------------------------------------------------------------------- #
# Loading and discovery
# --------------------------------------------------------------------------- #


def load_research_surface(
    db_root: Path,
    strategy_type: str,
    memory_version: str,
) -> tuple[pl.DataFrame, dict[str, Any]] | None:
    """Load the explicitly selected research surface for one version."""
    validate_identifier(strategy_type, "strategy_type")
    validate_memory_version(memory_version)
    version_root = Path(db_root) / "research" / "strategies" / strategy_type / memory_version
    pointer_path = version_root / "surface.json"
    if not pointer_path.is_file():
        return None

    pointer = json.loads(pointer_path.read_text())
    if not isinstance(pointer, dict) or pointer.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid research surface pointer: {pointer_path}")
    manifest_path = _resolve_inside(
        version_root,
        str(pointer.get("selected_manifest") or ""),
        label="selected_manifest",
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"research surface manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"invalid research surface manifest: {manifest_path}")
    required_text = ("experiment", "run_id", "published_at", "title", "summary")
    if any(not isinstance(manifest.get(key), str) or not manifest[key] for key in required_text):
        raise ValueError("research surface manifest is missing required text fields")
    if any(key not in manifest for key in ("benchmark", "performance", "metrics")):
        raise ValueError("research surface manifest is missing result fields")
    if not all(isinstance(manifest.get(key), list) for key in ("diagnostics", "gates", "disclosures", "provenance")):
        raise ValueError("research surface manifest has invalid display collections")
    _validate_display_collections(manifest["diagnostics"], manifest["gates"])
    for payload in (pointer, manifest):
        if payload.get("strategy_type") != strategy_type or payload.get("memory_version") != memory_version:
            raise ValueError("research surface identity does not match its directory")
        if payload.get("state") not in {"candidate", "rejected"}:
            raise ValueError("research surface has an invalid lifecycle state")
    if pointer["state"] != manifest["state"]:
        raise ValueError("research surface pointer and manifest states do not match")

    performance_meta = manifest.get("performance")
    performance_unit = manifest.get("performance_unit")
    pnl_meta = manifest.get("pnl")
    grid = manifest.get("grid")
    benchmark = manifest.get("benchmark")
    metrics = manifest.get("metrics")
    if performance_meta is None:
        if performance_unit is not None:
            raise ValueError("non-performance research record contains performance_unit")
        if metrics is not None or grid is not None:
            raise ValueError("text-only research record contains performance metadata")
        if pnl_meta is None:
            if benchmark is not None:
                raise ValueError("text-only research record contains a benchmark")
            frame = pl.DataFrame()
        else:
            if not isinstance(pnl_meta, dict):
                raise ValueError("research surface manifest has invalid PnL metadata")
            _validate_pnl_metadata(pnl_meta)
            pnl_path = _resolve_inside(
                version_root,
                str(pnl_meta.get("path") or ""),
                label="pnl.path",
            )
            frame = validate_pnl_frame(pl.read_parquet(pnl_path))
            if frame.height != pnl_meta.get("row_count") or frame.columns != pnl_meta.get("columns"):
                raise ValueError("research PnL metadata does not match its parquet")
            has_pnl_benchmark = PNL_BENCHMARK_COLUMN in frame.columns
            has_benchmark_metadata = (
                isinstance(benchmark, dict) and bool(benchmark.get("id")) and bool(benchmark.get("label"))
            )
            if has_pnl_benchmark != has_benchmark_metadata:
                raise ValueError("research PnL benchmark metadata does not match its parquet")
    else:
        if performance_unit is None:
            performance_unit = "usd"
            manifest["performance_unit"] = performance_unit
        if performance_unit not in {"usd", "index"}:
            raise ValueError("research surface manifest has an invalid performance_unit")
        if pnl_meta is not None:
            raise ValueError("research surface cannot contain both performance and PnL metadata")
        if not isinstance(performance_meta, dict):
            raise ValueError("research surface manifest has invalid performance metadata")
        if not isinstance(benchmark, dict) or not benchmark.get("id") or not benchmark.get("label"):
            raise ValueError("research surface manifest has an invalid benchmark")
        if not isinstance(metrics, dict) or not all(
            isinstance(metrics.get(key), dict) for key in ("strategy", "benchmark")
        ):
            raise ValueError("research surface manifest has invalid metrics")
        performance_path = _resolve_inside(
            version_root,
            str(performance_meta.get("path") or ""),
            label="performance.path",
        )
        frame = validate_performance_frame(pl.read_parquet(performance_path))
        if frame.height != performance_meta.get("row_count") or frame.columns != performance_meta.get("columns"):
            raise ValueError("research performance metadata does not match its parquet")
    if grid is not None:
        if not isinstance(grid, dict):
            raise ValueError("research surface grid metadata must be an object")
        summary_meta = grid.get("summary")
        if not isinstance(summary_meta, dict):
            raise ValueError("research grid summary metadata is missing")
        summary_path = _resolve_inside(
            version_root,
            str(summary_meta.get("path") or ""),
            label="grid.summary.path",
        )
        summary = validate_grid_summary(pl.read_parquet(summary_path), grid)
        if summary.height != summary_meta.get("row_count") or summary.columns != summary_meta.get("columns"):
            raise ValueError("research grid summary metadata does not match its parquet")
        series_path, series = _validate_grid_series(version_root, grid)
        series_rows = cast(
            pl.DataFrame,
            pl.scan_parquet(series_path).select(pl.len()).collect(),
        ).item()
        if series_rows != series.get("row_count"):
            raise ValueError("research grid series row count does not match its metadata")
    baseline = None
    with contextlib.suppress(OSError, TypeError, ValueError, json.JSONDecodeError):
        baseline = load_research_baseline(db_root, strategy_type)
    strategy_root = Path(db_root) / "research" / "strategies" / strategy_type
    manifest = {
        **manifest,
        "operator_baseline": bool(
            baseline is not None
            and baseline.get("memory_version") == memory_version
            and baseline.get("selected_run_id") == manifest.get("run_id")
            and baseline.get("selected_manifest") == manifest_path.relative_to(strategy_root).as_posix()
        ),
    }
    return frame, manifest


def discover_research_strategy_versions(db_root: Path) -> list[dict[str, Any]]:
    """Discover only research versions with complete, valid selected surfaces.

    Family directories starting with ``_`` (``_archive``) are retired and never listed.
    """
    root = Path(db_root) / "research" / "strategies"
    if not root.exists():
        return []
    discovered: list[dict[str, Any]] = []
    for pointer_path in sorted(root.glob("[!_]*/v*/surface.json")):
        strategy_type = pointer_path.parents[1].name
        memory_version = pointer_path.parent.name
        try:
            loaded = load_research_surface(db_root, strategy_type, memory_version)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pl.exceptions.PolarsError):
            continue
        if loaded is None:
            continue
        frame, manifest = loaded
        metrics = manifest.get("metrics")
        strategy_metrics = metrics["strategy"] if isinstance(metrics, dict) else {}
        discovered.append(
            {
                "strategy_type": strategy_type,
                "memory_version": memory_version,
                "total_runs": 1,
                "has_final": False,
                "best_sharpe": strategy_metrics.get("sharpe"),
                "best_return": strategy_metrics.get("total_return"),
                "final_run_id": None,
                "latest_run": manifest["published_at"],
                "state": manifest["state"],
                "display_state": research_display_state(manifest),
                "operator_baseline": manifest.get("operator_baseline") is True,
                "source": "research",
                "selected_run_id": manifest["run_id"],
                "experiment": manifest["experiment"],
                "has_surface": True,
                "surface_rows": frame.height,
            }
        )
    return discovered


def discover_invalidated_research_versions(db_root: Path) -> list[dict[str, Any]]:
    """Discover preserved research versions whose latest attempt is explicitly NOT TESTED."""
    root = Path(db_root) / "research" / "strategies"
    if not root.exists():
        return []
    discovered: list[dict[str, Any]] = []
    for version_root in sorted(root.glob("[!_]*/v*")):
        dispositions: list[tuple[str, Path, dict[str, Any]]] = []
        for path in version_root.glob("**/NOT_TESTED.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict) or payload.get("classification") != "NOT TESTED":
                continue
            detected_at = payload.get("detected_at_utc")
            ordering = detected_at if isinstance(detected_at, str) else path.parent.name
            dispositions.append((ordering, path, payload))
        if not dispositions:
            continue
        _, path, payload = max(dispositions, key=lambda item: (item[0], item[1].parent.name))
        scored = payload.get("scored_observations")
        discovered.append(
            {
                "strategy_type": version_root.parent.name,
                "memory_version": version_root.name,
                "total_runs": len(dispositions),
                "has_final": False,
                "best_sharpe": None,
                "best_return": None,
                "final_run_id": None,
                "latest_run": payload.get("detected_at_utc"),
                "state": "invalidated",
                "display_state": "invalidated",
                "source": "research",
                "selected_run_id": path.parent.name,
                "experiment": path.parent.parent.name,
                "has_surface": False,
                "surface_rows": 0,
                "invalidation_reason": payload.get("reason"),
                "scored_observations": scored if isinstance(scored, int) else None,
            }
        )
    return discovered


def discover_strategy_lifecycle_versions(
    strategy_types: Sequence[str],
    *,
    strategy_library_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Discover registered optimization versions for strategy families already in the database."""
    root = strategy_library_root or STRATEGY_LIBRARY_ROOT
    discovered: list[dict[str, Any]] = []
    for strategy_type in sorted(set(strategy_types)):
        try:
            validate_identifier(strategy_type, "strategy_type")
        except ValueError:
            continue
        optimization_root = root / strategy_type / "optimization"
        for version_path in sorted(optimization_root.glob("**/VERSION.toml")):
            memory_version = version_path.parent.name
            try:
                validate_memory_version(memory_version)
                payload = tomllib.loads(version_path.read_text())
            except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError):
                continue
            phase = payload.get("phase")
            status = payload.get("status")
            if (
                payload.get("version") not in (int(memory_version[1:]), memory_version)
                or not isinstance(phase, str)
                or not phase
                or not isinstance(status, str)
                or not status
            ):
                continue
            state = "invalidated" if status == "not_tested" else "candidate"
            discovered.append(
                {
                    "strategy_type": strategy_type,
                    "memory_version": memory_version,
                    "total_runs": 0,
                    "has_final": False,
                    "best_sharpe": None,
                    "best_return": None,
                    "final_run_id": None,
                    "latest_run": None,
                    "state": state,
                    "display_state": state,
                    "source": "research",
                    "selected_run_id": None,
                    "experiment": None,
                    "has_surface": False,
                    "surface_rows": 0,
                    "lifecycle_phase": phase,
                    "lifecycle_status": status,
                    "invalidation_reason": payload.get("finding") if status == "not_tested" else None,
                }
            )
    return discovered


def discover_strategy_versions_with_research(
    db_root: Path,
    *,
    strategy_library_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge canonical, surfaced, invalidated, and registered research versions."""
    merged = {
        (row["strategy_type"], row["memory_version"]): {
            **row,
            "state": "promoted",
            "display_state": "promoted",
            "source": "canonical",
            "selected_run_id": row.get("final_run_id"),
            "experiment": None,
            "has_surface": False,
        }
        for row in discover_strategy_versions(db_root)
    }
    for row in discover_research_strategy_versions(db_root):
        merged.setdefault((row["strategy_type"], row["memory_version"]), row)
    for row in discover_invalidated_research_versions(db_root):
        merged.setdefault((row["strategy_type"], row["memory_version"]), row)
    for row in discover_strategy_lifecycle_versions(
        [strategy_type for strategy_type, _ in merged],
        strategy_library_root=strategy_library_root,
    ):
        merged.setdefault((row["strategy_type"], row["memory_version"]), row)
    return sorted(merged.values(), key=lambda row: (row["strategy_type"], row["memory_version"]))
