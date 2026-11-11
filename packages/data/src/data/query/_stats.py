"""Numeric stats in one pass: DuckDB SQL for collections, Polars expressions for one file.

Both engines produce the same one-row frame (`total` plus `c<i>_<stat>` per column), which
`stats_frame_from_row` reshapes into one row per column.

USAGE:
    sql = numeric_stats_sql(table_sql="read_parquet([...])", columns=["close"])
    row = lazy_frame.select(numeric_stats_exprs(["close"], schema)).collect()
    frame = stats_frame_from_row(row, ["close"])
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl

from ._sql import quote_ident

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

_STATS = ("n", "mean", "std", "min", "max", "median")
_FLOAT_STATS = ("mean", "std", "min", "max", "median")


def empty_numeric_stats_frame() -> pl.DataFrame:
    """Return the standard empty numeric-stats frame."""
    return pl.DataFrame(
        schema={
            "column": pl.String,
            "count": pl.Int64,
            "null_count": pl.Int64,
            "mean": pl.Float64,
            "std": pl.Float64,
            "min": pl.Float64,
            "max": pl.Float64,
            "median": pl.Float64,
        }
    )


# --------------------------------------------------------------------------- #
# One-pass builders
# --------------------------------------------------------------------------- #


def numeric_stats_sql(*, table_sql: str, columns: Sequence[str]) -> str:
    """One DuckDB scan computing every column's stats (a UNION ALL would scan once per column)."""
    selects = ["count(*) AS total"]
    for index, column in enumerate(columns):
        ident = quote_ident(column)
        selects += [
            f"count({ident}) AS c{index}_n",
            f"avg({ident}) AS c{index}_mean",
            f"stddev_samp({ident}) AS c{index}_std",
            f"min({ident}) AS c{index}_min",
            f"max({ident}) AS c{index}_max",
            f"median({ident}) AS c{index}_median",
        ]
    return f"SELECT {', '.join(selects)} FROM {table_sql}"


def numeric_stats_exprs(
    columns: Sequence[str],
    schema: Mapping[str, pl.DataType],
) -> list[pl.Expr]:
    """The same one-row result as `numeric_stats_sql`, as Polars expressions.

    DuckDB orders NaN above every number, so a float column holding NaN has max NaN;
    `nan_max` matches that, while Polars' plain `max` would skip the NaN.
    """
    exprs = [pl.len().alias("total")]
    for index, column in enumerate(columns):
        col = pl.col(column)
        is_float = schema[column] in (pl.Float32, pl.Float64)
        exprs += [
            col.count().alias(f"c{index}_n"),
            col.mean().alias(f"c{index}_mean"),
            col.std().alias(f"c{index}_std"),
            col.min().alias(f"c{index}_min"),
            (col.nan_max() if is_float else col.max()).alias(f"c{index}_max"),
            col.median().alias(f"c{index}_median"),
        ]
    return exprs


def stats_frame_from_row(row_frame: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """Reshape the one-row result into one row per column with the standard schema."""
    row = row_frame.row(0, named=True)
    total = int(row["total"])
    records = []
    for index, column in enumerate(columns):
        values = {stat: row[f"c{index}_{stat}"] for stat in _STATS}
        records.append(
            {
                "column": column,
                "count": total,
                "null_count": total - int(values["n"]),
                **{stat: None if values[stat] is None else float(values[stat]) for stat in _FLOAT_STATS},
            }
        )
    return pl.DataFrame(records, schema=empty_numeric_stats_frame().schema)
