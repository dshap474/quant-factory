"""Read the named control from a selected research run without rewriting its surface.

USAGE: ``comparison, issue = load_run_comparison(db_root, manifest, performance)``.
Only the declared control and date-paired return artifacts are eligible.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import json
from pathlib import Path
from typing import Any

import polars as pl
from data.query import ParquetQuery, QueryError, query_parquet
from strategies.research_surface import summarize_returns


# --------------------------------------------------------------------------- #
# Selected-run comparison
# --------------------------------------------------------------------------- #
def load_run_comparison(
    db_root: Path, manifest: dict[str, Any], performance: pl.DataFrame
) -> tuple[dict[str, Any] | None, str | None]:
    """Expose a same-run control only when its identity and candidate pairing agree."""
    labels = [
        item.get("value")
        for item in manifest.get("provenance", [])
        if isinstance(item, dict) and item.get("label") == "control"
    ]
    if len(labels) != 1 or not isinstance(labels[0], str) or not labels[0].strip():
        return None, None
    if performance.is_empty() or "strategy_daily_return" not in performance.columns:
        return None, None
    label = labels[0].strip()
    try:
        root = (Path(db_root) / "research").resolve()
        version = root / "strategies" / manifest["strategy_type"] / manifest["memory_version"]
        run = version / manifest["experiment"] / manifest["run_id"]
        names = ("surface/manifest.json", "candidate_returns.parquet", "control_returns.parquet")
        files = {name: run / name for name in names}
        if not files["control_returns.parquet"].is_file():
            return None, None
        for path in files.values():
            if not path.resolve().is_relative_to(version.resolve()) or any(
                part.is_symlink() for part in (path, *path.parents) if part != root
            ):
                raise ValueError("comparison path escapes the selected version")
        selected = json.loads((version / "surface.json").read_text())
        if selected["selected_manifest"] != files["surface/manifest.json"].relative_to(version).as_posix():
            raise ValueError("comparison does not belong to the selected run")
        frames = []
        for name in names[1:]:
            result = query_parquet(
                ParquetQuery(
                    scope="research",
                    path=files[name].relative_to(root).as_posix(),
                    columns=("session_date", "net_return"),
                    order_by="session_date",
                    limit=performance.height + 1,
                ),
                db_root=db_root,
            ).frame.rename({"session_date": "date"})
            if result.height != performance.height or not result["date"].equals(performance["date"]):
                raise ValueError("comparison dates do not match the selected surface")
            if result["net_return"].null_count() or not result["net_return"].is_finite().all():
                raise ValueError("comparison contains invalid returns")
            frames.append(result)
        candidate, control = frames
        if not candidate["net_return"].equals(performance["strategy_daily_return"].rename("net_return")):
            raise ValueError("comparison candidate differs from the selected surface")
        metrics = summarize_returns(control["net_return"].to_list())
        data = control.select(
            "date",
            pl.col("net_return").alias("daily_return"),
            ((1 + pl.col("net_return")).cum_prod() * 100).alias("portfolio_value"),
        )
        return {
            "id": "registered_control",
            "label": label,
            "run_id": manifest["run_id"],
            "metrics": metrics,
            "data": data,
        }, None
    except (KeyError, OSError, TypeError, ValueError, QueryError, pl.exceptions.PolarsError):
        return None, f"{label}: verified comparison returns are unavailable."
