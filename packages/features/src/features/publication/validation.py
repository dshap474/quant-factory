"""Feature dataset validation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import polars as pl

TIMESTAMP_COL = "timestamp"
ASSET_COL = "asset"


def _dtype_is_datetime(dtype: pl.DataType) -> bool:
    return str(dtype).startswith("Datetime")


def ensure_timestamp_datetime(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure ``timestamp`` exists and is ``Datetime(us)``."""
    if TIMESTAMP_COL not in df.columns:
        raise ValueError("Feature output must include 'timestamp' column")

    dtype = df[TIMESTAMP_COL].dtype
    if dtype == pl.Date:
        return df.with_columns(pl.col(TIMESTAMP_COL).cast(pl.Datetime("us")))
    if _dtype_is_datetime(dtype):
        return df.with_columns(pl.col(TIMESTAMP_COL).cast(pl.Datetime("us")))
    if dtype == pl.Utf8:
        return df.with_columns(pl.col(TIMESTAMP_COL).str.to_datetime().cast(pl.Datetime("us")))

    raise ValueError(f"Feature 'timestamp' must be Datetime/Date/Utf8 parseable datetime, got {dtype}")


def validate_feature_frame(
    df: pl.DataFrame,
    *,
    require_asset: bool,
    category: str,
    label_columns: Sequence[str] = (),
) -> pl.DataFrame:
    """Validate the canonical feature frame contract.

    ``label_columns`` are family-declared String descriptor columns (for example a
    per-row ``return_basis``); they are exempt from the numeric check but must be
    present and String-typed. Every other non-key column must be numeric.
    """
    if not isinstance(df, pl.DataFrame):
        raise TypeError(f"Feature compute for '{category}' must return pl.DataFrame")

    df = ensure_timestamp_datetime(df)

    if require_asset and ASSET_COL not in df.columns:
        raise ValueError(f"Feature category '{category}' requires 'asset' column but it is missing")
    if not require_asset and ASSET_COL in df.columns:
        raise ValueError(f"Feature category '{category}' must not include 'asset' column")

    for column in label_columns:
        if column not in df.columns:
            raise ValueError(f"Declared label column '{column}' is missing from '{category}' output")
        if df[column].dtype != pl.Utf8:
            raise ValueError(f"Label column '{column}' in '{category}' must be String, got {df[column].dtype}")
    non_feature_cols = {TIMESTAMP_COL, ASSET_COL, *label_columns}
    feature_cols = [column for column in df.columns if column not in non_feature_cols]
    if not feature_cols:
        raise ValueError(f"Feature output for '{category}' contains no feature columns")
    for column in feature_cols:
        dtype = df[column].dtype
        if hasattr(dtype, "is_numeric") and dtype.is_numeric():
            continue
        if any(token in str(dtype) for token in ("Int", "UInt", "Float", "Decimal")):
            continue
        raise ValueError(f"Feature column '{column}' in '{category}' must be numeric, got {dtype}")

    ordered = [TIMESTAMP_COL]
    if ASSET_COL in df.columns:
        ordered.append(ASSET_COL)
    ordered.extend([column for column in df.columns if column not in ordered])
    return df.select(ordered)


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"
