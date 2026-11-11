"""Tests for read-only dataset query endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def db_api_root(tmp_path: Path) -> Path:
    db_root = tmp_path / "db"
    target = db_root / "data" / "raw" / "1d"
    target.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(4)],
            "asset": ["BTC", "ETH", "BTC", "SOL"],
            "observation_date": [
                (datetime(2024, 1, 1) + timedelta(days=i)).date().isoformat()
                for i in range(4)
            ],
            "close": [10.0, 20.0, 11.0, 30.0],
            "volume": [100, 200, 110, 300],
        }
    ).write_parquet(target / "panel.parquet")
    return db_root


def test_schema_endpoint(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get("/api/datasets/data/schema/raw/1d/panel.parquet")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_rows"] == 4
    assert {column["name"] for column in payload["schema"]} == {
        "timestamp",
        "asset",
        "observation_date",
        "close",
        "volume",
    }


def test_schema_endpoint_rejects_removed_polars_backend_param(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/schema/raw/1d/panel.parquet",
        params={"backend": "polars"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "data.query chooses the engine; backend is not a parameter"


def test_query_endpoint_filters_projects_and_limits(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/query/raw/1d/panel.parquet",
        params={
            "columns": "timestamp,asset,close",
            "entity_column": "asset",
            "entity_value": ["BTC"],
            "order_by": "timestamp",
            "descending": True,
            "limit": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "polars"
    assert payload["returned_rows"] == 1
    assert payload["data"][0]["asset"] == "BTC"
    assert payload["data"][0]["close"] == 11.0
    # matched_rows counts every filtered row, ignoring limit; total_rows stays the file size.
    assert payload["matched_rows"] < payload["total_rows"]
    assert payload["matched_rows"] > payload["returned_rows"]


def test_query_endpoint_rejects_removed_polars_backend_param(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/query/raw/1d/panel.parquet",
        params={"backend": "polars", "limit": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "data.query chooses the engine; backend is not a parameter"


def test_query_endpoint_returns_400_for_invalid_temporal_bound(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/query/raw/1d/panel.parquet",
        params={"start": "not-a-date"},
    )

    assert response.status_code == 400
    assert "Invalid temporal bound" in response.json()["detail"]


def test_arrow_endpoint_returns_ipc(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/arrow/raw/1d/panel.parquet",
        params={"columns": "asset,close", "limit": 2},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.apache.arrow.file"
    assert response.headers["x-returned-rows"] == "2"
    assert response.content.startswith(b"ARROW")


def test_stats_endpoint(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get(
        "/api/datasets/data/stats/raw/1d/panel.parquet",
        params={"columns": "close"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["column"] == "close"
    assert payload["data"][0]["count"] == 4


def test_path_traversal_is_rejected(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get("/api/datasets/data/schema/../outside.parquet")

    assert response.status_code in {403, 404}
