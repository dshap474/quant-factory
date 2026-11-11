"""Shared test fixtures for the DB API."""

from pathlib import Path

import pytest
from db_api.config import settings
from db_api.dataset_charts import clear_chart_caches
from db_api.dataset_index import clear_parquet_indexes
from db_api.main import create_app
from db_api.routers.backtests import (
    _cached_discover_saved_backtests,
    _cached_discover_strategy_versions,
)
from db_api.routers.catalog import _cached_catalog_overview, _cached_catalog_stats, _cached_logical_catalog
from db_api.routers.docs import _cached_doc_page, _cached_docs_tree
from db_api.routers.features import _cached_discover_features, _cached_feature_browser_stats
from db_api.routers.research import (
    _cached_research_doc,
)
from db_api.routers.signals import (
    _cached_discover_signal_research_versions,
    _cached_discover_signals,
)
from fastapi.testclient import TestClient

app = create_app(load_extensions=False)


def _clear_router_caches() -> None:
    for fn in (
        _cached_discover_saved_backtests,
        _cached_discover_strategy_versions,
        _cached_discover_features,
        _cached_discover_signal_research_versions,
        _cached_discover_signals,
        _cached_feature_browser_stats,
        _cached_catalog_stats,
        _cached_catalog_overview,
        _cached_logical_catalog,
        _cached_docs_tree,
        _cached_doc_page,
        _cached_research_doc,
    ):
        clear = getattr(fn, "cache_clear", None)
        if callable(clear):
            clear()
    clear_parquet_indexes()
    clear_chart_caches()


@pytest.fixture(autouse=True)
def clear_caches_between_tests():
    _clear_router_caches()
    yield
    _clear_router_caches()


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def set_db_root(monkeypatch):
    """Set settings.db_root for a test."""

    def _setter(path: Path) -> None:
        monkeypatch.setattr(settings, "db_root", path)
        monkeypatch.setattr(settings, "repo_root", path.parent)
        _clear_router_caches()

    return _setter
