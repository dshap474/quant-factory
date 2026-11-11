"""Verify scoped history precedence and strict compatibility independently of seeds.

USAGE: uv run pytest packages/data/tests/unit/test_asset_identity_resolution.py -q
"""
from datetime import date
from pathlib import Path
import polars as pl
import pytest
from data.platform.asset_mapper import resolution
from data.platform.errors import DatasetContractError

# --------------------------------------------------------------------------- #
# Historical examples
# --------------------------------------------------------------------------- #
@pytest.fixture
def aliases(monkeypatch):
    ids = pl.DataFrame({
        "asset_id": ["crypto:global", "crypto:scoped"],
        "identifier_type": ["yfinance_symbol"] * 2,
        "identifier_value": ["SAME"] * 2,
        "venue": [None, "VENUE"],
        "valid_from": [date(2020, 1, 1), date(2022, 1, 1)],
        "valid_to": [None, date(2023, 1, 1)],
    })
    monkeypatch.setattr(resolution, "load_asset_identity", lambda root: (pl.DataFrame(), ids, "test"))
    return ids


def resolve(frame, **kwargs):
    return resolution.resolve_asset_ids(frame, db_root=Path("unused"), identifier_type="yfinance_symbol",
        identifier_column="symbol", as_of_column="date", allow_missing=True, **kwargs)


def test_mixed_venues_preserve_scoped_gaps_and_rows(aliases):
    frame = pl.DataFrame({"symbol": ["same"] * 5,
        "date": [date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1), date(2022, 1, 1), date(2022, 1, 1)],
        "exchange": ["venue", " VENUE ", "venue", "other", None]})
    got = resolve(frame, venue_column="exchange", venue_fallback=True)
    assert got["asset_id"].to_list() == [None, "crypto:scoped", None, "crypto:global", "crypto:global"]
    assert got.drop("asset_id").equals(frame)


def test_default_stays_exact_and_conflicting_arguments_fail(aliases):
    frame = pl.DataFrame({"symbol": ["SAME"], "date": [date(2022, 1, 1)]})
    assert resolve(frame, venue="other")["asset_id"].item() is None
    assert resolve(frame)["asset_id"].item() == "crypto:global"
    with pytest.raises(DatasetContractError, match="not both"):
        resolve(frame, venue="VENUE", venue_column="exchange")


def test_ambiguity_never_selects_first(monkeypatch, aliases):
    duplicate = aliases.filter(pl.col("venue") == "VENUE").with_columns(pl.lit("crypto:wrong").alias("asset_id"))
    monkeypatch.setattr(resolution, "load_asset_identity", lambda root: (pl.DataFrame(), pl.concat([aliases, duplicate]), "test"))
    frame = pl.DataFrame({"symbol": ["SAME"], "date": [date(2022, 1, 1)]})
    with pytest.raises(DatasetContractError, match="ambiguously"):
        resolve(frame, venue="VENUE", venue_fallback=True)
