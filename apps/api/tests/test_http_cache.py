"""Tests for HTTP cache-control headers on the read-only API."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from db_api.http_cache import cache_control_for, register_no_store_prefix


@pytest.fixture
def db_api_root(tmp_path: Path) -> Path:
    db_root = tmp_path / "db"
    target = db_root / "data" / "raw" / "1d"
    target.mkdir(parents=True)
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "index.md").write_text("# Docs\n", encoding="utf-8")
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(3)],
            "close": [10.0, 20.0, 30.0],
        }
    ).write_parquet(target / "panel.parquet")
    return db_root


def test_discovery_reads_get_sixty_second_private_cache(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    for url in (
        "/api/datasets/data/schema/raw/1d/panel.parquet",
        "/api/catalog",
        "/api/docs/tree",
        "/api/docs/page/index.md",
    ):
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, max-age=60"


def test_data_payload_reads_always_revalidate(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    for url in (
        "/api/datasets/data/preview/raw/1d/panel.parquet",
        "/api/datasets/data/query/raw/1d/panel.parquet",
        "/api/datasets/data/stats/raw/1d/panel.parquet",
        "/api/datasets/data/arrow/raw/1d/panel.parquet",
    ):
        response = client.get(url)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-cache"


def test_health_is_never_stored(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


def test_error_responses_carry_no_cache_headers(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.get("/api/datasets/data/schema/raw/1d/missing.parquet")

    assert response.status_code == 404
    assert "Cache-Control" not in response.headers


def test_non_get_responses_carry_no_cache_headers(client, set_db_root, db_api_root):
    set_db_root(db_api_root)

    response = client.post("/api/catalog/refresh")

    assert response.status_code == 200
    assert "Cache-Control" not in response.headers


def test_cache_control_policy_covers_route_classes():
    assert cache_control_for("/health") == "no-store"
    register_no_store_prefix("/api/live-example")
    assert cache_control_for("/api/live-example/tape") == "no-store"
    assert cache_control_for("/api/catalog/logical") == "private, max-age=60"
    assert cache_control_for("/api/catalog/browse/raw/1d") == "private, max-age=60"
    assert cache_control_for("/api/features/browser/example-panel") == "private, max-age=60"
    assert cache_control_for("/api/datasets/features/schema/panel.parquet") == "private, max-age=60"
    assert cache_control_for("/api/catalog/chart/raw/1d/panel.parquet") == "private, no-cache"
    assert cache_control_for("/api/backtests") == "private, no-cache"
    assert cache_control_for("/api/production/series") == "private, no-cache"
    assert cache_control_for("/openapi.json") is None


def test_explicit_no_store_survives_default_api_policy():
    from db_api.http_cache import CacheControlMiddleware
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(CacheControlMiddleware)

    @app.get("/api/test-stream")
    def stream():
        return StreamingResponse(
            iter(["data: {}\n\n"]), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
        )

    response = TestClient(app).get("/api/test-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.text == "data: {}\n\n"
