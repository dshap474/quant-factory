"""Tests for catalog API endpoints."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from db_api.catalog_labels import register_raw_family_rule
from db_api.routers import catalog as catalog_router


@pytest.fixture
def catalog_db_root():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_root = Path(tmp_dir)
        (db_root / "signals").mkdir(parents=True)
        (db_root / "data" / ".hidden").mkdir(parents=True)
        nested = db_root / "data" / "raw" / "1d" / "macro"
        nested.mkdir(parents=True)
        index_dir = db_root / "data" / "raw" / "1d" / "index"
        index_dir.mkdir(parents=True)
        custom_dir = db_root / "data" / "raw" / "1d" / "custom"
        custom_dir.mkdir(parents=True)
        misc_dir = db_root / "data" / "raw" / "1d" / "misc"
        misc_dir.mkdir(parents=True)
        derived = db_root / "data" / "derived" / "1d" / "crypto" / "depth"
        derived.mkdir(parents=True)
        derived_1m = db_root / "data" / "derived" / "1m" / "crypto" / "depth"
        derived_1m.mkdir(parents=True)
        equities_derived = db_root / "data" / "derived" / "1d" / "equities" / "example" / "reference"
        equities_derived.mkdir(parents=True)
        macro_derived = db_root / "data" / "derived" / "1d" / "macro" / "rates"
        macro_derived.mkdir(parents=True)
        features = db_root / "features" / "1d" / "equities" / "value-panel"
        features.mkdir(parents=True)

        pl.DataFrame({"x": [1, 2, 3, 4], "y": [3.0, 4.0, 5.0, 6.0]}).write_parquet(nested / "data.parquet")
        pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(4)],
                "close": [100.0, 101.5, 102.2, 99.8],
            }
        ).write_parquet(index_dir / "btc.parquet")
        pl.DataFrame(
            {
                "timestamp": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 3),
                ],
                "symbol": ["A", "B", "A", "B", "A"],
                "open": [10.0, 20.0, 11.0, 21.0, 12.0],
                "close": [11.0, 19.5, 12.0, 20.5, 13.0],
                "volume": [1000, 500, 1200, 450, 1300],
                "funding_rate": [0.001, -0.001, 0.002, -0.002, 0.003],
                "market_cap_usd": [100.0, 80.0, 110.0, 75.0, 130.0],
            }
        ).write_parquet(custom_dir / "equities.parquet")
        pl.DataFrame({"label": ["x", "y"], "category": ["a", "b"]}).write_parquet(misc_dir / "non_chartable.parquet")
        pl.DataFrame({"mid": [10.0, 10.5], "spread": [1.0, 1.2]}).write_parquet(derived / "data.parquet")
        pl.DataFrame({"mid": [10.0, 10.5], "spread": [1.0, 1.2]}).write_parquet(derived_1m / "data.parquet")
        pl.DataFrame({"cik": ["0001"], "ticker": ["ABC"]}).write_parquet(equities_derived / "entity_reference.parquet")
        pl.DataFrame({"date": [datetime(2024, 1, 1)], "value": [4.2]}).write_parquet(
            macro_derived / "index_daily.parquet"
        )
        pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "flow": [1.0]}).write_parquet(features / "data.parquet")
        (db_root / "data" / "derived" / "REGISTRY.yaml").write_text(
            """
version: 5
categories:
  crypto/depth:
    description: Example depth data
    resolutions: [1d, 1m]
    status: active
    asset_column: false
datasets:
  1d/crypto/depth:
    description: Example depth data
    status: active
    data_path: data/derived/1d/crypto/depth/data.parquet
    updated_at: '2026-05-15T00:00:00+00:00'
  1m/crypto/depth:
    description: Example depth data
    status: active
    data_path: data/derived/1m/crypto/depth/data.parquet
    updated_at: '2026-05-15T00:00:00+00:00'
""".strip(),
            encoding="utf-8",
        )
        (db_root / "features" / "REGISTRY.yaml").write_text(
            """
version: 5
categories:
  equities/value-panel:
    description: Equities value feature set
    resolutions: [1d]
    status: active
    asset_column: false
features:
  1d/equities/value-panel:
    description: Equities value feature set
    status: active
    data_path: features/1d/equities/value-panel/data.parquet
    updated_at: '2026-05-15T00:00:00+00:00'
""".strip(),
            encoding="utf-8",
        )
        (nested / "README.md").write_text("# Macro data\n\nThis is a test readme.\n")
        (db_root / "signals" / "notes.txt").write_text("hello")

        yield db_root


def test_list_root_excludes_hidden_entries(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()

    names = {item["name"] for item in payload["items"]}
    assert "raw" in names
    assert ".hidden" not in names


def test_browse_directory(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/browse/raw/1d/macro")
    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == "raw/1d/macro"
    item_names = {item["name"] for item in payload["items"]}
    assert {"data.parquet", "README.md"} <= item_names


def test_preview_parquet(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/datasets/data/preview/raw/1d/macro/data.parquet?page=2&page_size=2")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "raw/1d/macro/data.parquet"
    assert payload["total_rows"] == 4
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    assert payload["total_pages"] == 2
    assert payload["has_prev"] is True
    assert payload["has_next"] is False
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["x"] == 3


def test_preview_markdown(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/markdown/raw/1d/macro/README.md")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "raw/1d/macro/README.md"
    assert payload["lines"] == 3
    assert "Macro data" in payload["content"]


def test_schema_parquet(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/datasets/data/schema/raw/1d/macro/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    column_names = {col["name"] for col in payload["schema"]}
    assert {"x", "y"} <= column_names


def test_catalog_stats(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/stats")
    assert response.status_code == 200
    payload = response.json()

    assert payload["parquet_files"] == 8
    assert payload["directories"]["raw"] == 4
    assert payload["directories"]["derived"] == 4


def test_catalog_overview(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/overview")
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["parquet_files"] == 8
    branch_names = {branch["name"] for branch in payload["branches"]}
    assert {"raw", "derived"} <= branch_names

    raw_branch = next(branch for branch in payload["branches"] if branch["name"] == "raw")
    assert raw_branch["path"] == "raw"
    assert raw_branch["children"][0]["name"] == "1d"

    featured_paths = {surface["path"] for surface in payload["featured_surfaces"]}
    assert "raw/1d" in featured_paths
    assert "derived/1d/crypto" in featured_paths


def test_logical_catalog_groups_registry_items(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/logical")
    assert response.status_code == 200
    payload = response.json()

    items = {item["id"]: item for item in payload["items"]}
    orderbook = items["dataset:crypto/depth"]
    assert orderbook["kind"] == "dataset"
    assert orderbook["layer"] == "derived"
    assert orderbook["label"] == "Depth"
    assert orderbook["domain"] == "crypto"
    assert [option["resolution"] for option in orderbook["resolutions"]] == ["1d", "1m"]
    assert orderbook["resolutions"][0]["scope"] == "data"
    assert orderbook["resolutions"][0]["path"] == "derived/1d/crypto/depth/data.parquet"

    entity_reference = items["dataset:equities/example/reference/entity_reference"]
    assert entity_reference["kind"] == "dataset"
    assert entity_reference["layer"] == "derived"
    assert entity_reference["domain"] == "equities"
    assert entity_reference["resolutions"][0]["path"] == "derived/1d/equities/example/reference/entity_reference.parquet"

    macro_item = items["dataset:macro/rates/index_daily"]
    assert macro_item["kind"] == "dataset"
    assert macro_item["layer"] == "derived"
    assert macro_item["domain"] == "macro"
    assert macro_item["resolutions"][0]["path"] == "derived/1d/macro/rates/index_daily.parquet"

    value_panel = items["feature_set:equities/value-panel"]
    assert value_panel["kind"] == "feature_set"
    assert value_panel["layer"] == "features"
    assert value_panel["label"] == "Value Panel"
    assert value_panel["domain"] == "equities"
    assert value_panel["resolutions"][0]["scope"] == "features"
    assert value_panel["resolutions"][0]["path"] == "1d/equities/value-panel/data.parquet"

    raw_macro = items["dataset:macro"]
    assert raw_macro["kind"] == "dataset"
    assert raw_macro["layer"] == "raw"
    assert raw_macro["domain"] == "macro"
    assert raw_macro["resolutions"][0]["scope"] == "data"
    assert raw_macro["resolutions"][0]["path"] == "raw/1d/macro/data.parquet"


def test_logical_catalog_summarizes_raw_storage_members(client, set_db_root, catalog_db_root, monkeypatch):
    monkeypatch.setattr(client.app.state, "raw_family_rules", (), raising=False)
    register_raw_family_rule(client.app, "provider-a", depth=3)
    register_raw_family_rule(client.app, "provider-b", depth=3, second_levels={"futures", "spot"})
    raw_root = catalog_db_root / "data" / "raw"
    frame = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "value": [1.0]})
    raw_paths = (
        raw_root / "1m" / "vendor" / "book" / "2024" / "01" / "btc_levels.parquet",
        raw_root / "1m" / "vendor" / "book" / "2024" / "02" / "btc_levels.parquet",
        raw_root / "1d" / "provider-b" / "futures" / "venue-x" / "btc_futures_venue-x.parquet",
        raw_root / "1d" / "provider-b" / "futures" / "venue-x" / "eth_futures_venue-x.parquet",
        raw_root / "1h" / "provider-b" / "futures" / "venue-x" / "btc_futures_venue-x.parquet",
        raw_root / "1d" / "provider-b" / "options" / "venue-x" / "btc_options.parquet",
        raw_root / "1d" / "provider-a" / "stocks" / "news" / "data.parquet",
        raw_root / "1d" / "provider-a" / "stocks" / "news" / "dt=2024-01-01" / "chunk-a.parquet",
        raw_root / "1d" / "example" / "filings" / "quarter=2019q4" / "table.parquet",
        raw_root / "1d" / "example" / "filings" / "quarter=2020q1" / "table.parquet",
    )
    for path in raw_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)
    set_db_root(catalog_db_root)

    response = client.get(
        "/api/catalog/logical",
        params={"kind": "dataset", "layer": "raw", "summary": True},
    )

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert "dataset:vendor/book/btc_levels" in items
    assert "dataset:provider-b/futures/venue-x" in items
    assert "dataset:provider-a/stocks/news" in items
    # A second level outside the rule falls back to the generic collapse.
    assert "dataset:provider-b/options/venue-x/btc_options" in items
    assert not any("/2024/01/" in item["category_path"] for item in items.values())
    assert not any("chunk-" in item["category_path"] for item in items.values())
    # Quarter partitions fold into one family per table, not one per quarter.
    assert "dataset:example/filings/table" in items
    assert not any("quarter=" in item["category_path"] for item in items.values())

    # Summary items carry one representative option per distinct resolution so the
    # web tree can place each family under every resolution directory it lives in.
    for item in items.values():
        assert len(item["resolutions"]) >= 1
    provider_b = items["dataset:provider-b/futures/venue-x"]
    assert [option["resolution"] for option in provider_b["resolutions"]] == ["1d", "1h"]
    assert provider_b["default_resolution"] is None
    vendor_book = items["dataset:vendor/book/btc_levels"]
    assert [option["resolution"] for option in vendor_book["resolutions"]] == ["1m"]
    assert vendor_book["resolutions"][0]["scope"] == "data"

    family_response = client.get(
        "/api/catalog/logical",
        params={
            "kind": "dataset",
            "layer": "raw",
            "family": "vendor/book/btc_levels",
        },
    )
    assert family_response.status_code == 200
    assert family_response.json()["total"] == 2


def test_logical_catalog_reads_resolution_from_direct_raw_contract(client, set_db_root, tmp_path):
    db_root = tmp_path / "db"
    family = db_root / "data" / "raw" / "example-feed"
    family.mkdir(parents=True)
    pl.DataFrame({"timestamp": [datetime(2026, 7, 1)], "close_usd": [1.0]}).write_parquet(family / "data.parquet")
    (family / "CONTRACT.yaml").write_text(
        """
datasets:
  example_feed.raw.price_volume_1d.v1:
    target: canonical_data_raw
    canonical_root: db/data/raw/example-feed
    canonical_artifact: data.parquet
    resolution: 1d
""".strip(),
        encoding="utf-8",
    )
    set_db_root(db_root)

    response = client.get("/api/catalog/logical", params={"kind": "dataset", "layer": "raw"})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == "dataset:example-feed"
    assert item["default_resolution"] == "1d"
    assert item["resolutions"][0]["path"] == "raw/example-feed/data.parquet"


def test_logical_catalog_filters_searches_and_paginates(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get(
        "/api/catalog/logical",
        params={"kind": "dataset", "layer": "derived", "q": "index", "limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["offset"] == 0
    assert payload["limit"] == 1
    assert payload["items"][0]["id"] == "dataset:macro/rates/index_daily"
    assert payload["facets"]["layers"] == ["derived", "raw"]
    assert {"crypto", "equities", "macro"} <= set(payload["facets"]["domains"])


def test_logical_catalog_facets_follow_prior_selections(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get(
        "/api/catalog/logical",
        params={"kind": "dataset", "layer": "raw", "domain": "custom"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["facets"]["layers"] == ["derived", "raw"]
    assert "custom" in payload["facets"]["domains"]
    assert payload["items"][0]["domain"] == "custom"


def test_logical_catalog_unfiltered_response_remains_complete(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    payload = client.get("/api/catalog/logical").json()

    assert payload["limit"] is None
    assert payload["total"] == len(payload["items"])
    assert {"dataset", "feature_set"} <= {item["kind"] for item in payload["items"]}


def test_refresh_rebuilds_only_runtime_indexes(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.post("/api/catalog/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "refreshed"
    assert payload["scopes"] == {"data": 8, "features": 1}
    assert "+00:00" in payload["refreshed_at"]


def test_logical_feature_catalog_groups_package_feature_sets(client, set_db_root, tmp_path, monkeypatch):
    db_root = tmp_path / "db"
    packages_root = tmp_path / "packages" / "features" / "extensions" / "lib"
    # `panel-composite` and `example-panel-b` are slugs whose registry
    # category is not their directory name with dashes swapped for underscores; they
    # stay in this fixture so the registered runner's category is exercised, not
    # just the fallback. The registered families are stubbed so the test does not
    # depend on which feature extensions are installed.
    monkeypatch.setattr(
        catalog_router,
        "PUBLISHABLE_FAMILIES",
        {
            "cross_sectional/composite": SimpleNamespace(
                category="cross_sectional/composite", runner_module="panel_composite.runner"
            ),
            "cross_sectional/panel_b": SimpleNamespace(
                category="cross_sectional/panel_b", runner_module="example_panel_b_features.runner"
            ),
        },
    )
    package_modules = {
        "btc": "example_crypto_features",
        "panel-composite": "panel_composite",
        "example-panel-b": "example_panel_b_features",
        "macro": "example_macro_features",
    }
    for package, module in package_modules.items():
        (packages_root / package / "src" / module).mkdir(parents=True)

    for feature_path in (
        db_root / "features" / "1d" / "btc",
        db_root / "features" / "1d" / "btc" / "slice-a",
        db_root / "features" / "1m" / "btc" / "slice-b",
        db_root / "features" / "1d" / "cross_sectional" / "composite",
        db_root / "features" / "1d" / "cross_sectional" / "panel_b",
        db_root / "features" / "1d" / "cross_sectional" / "panel_b" / "variant",
        db_root / "features" / "1d" / "macro",
    ):
        feature_path.mkdir(parents=True)
        pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "value": [1.0]}).write_parquet(feature_path / "data.parquet")

    (db_root / "features" / "REGISTRY.yaml").write_text(
        """
version: 5
categories:
  btc:
    description: BTC feature package
    resolutions: [1d]
    status: active
  btc/slice-a:
    description: Example slice A
    resolutions: [1d]
    status: active
  btc/slice-b:
    description: Example slice B
    resolutions: [1m]
    status: active
  cross_sectional/composite:
    description: Cross-sectional asset package
    resolutions: [1d]
    status: active
  cross_sectional/panel_b:
    description: Cross-sectional panel package
    resolutions: [1d]
    status: active
    asset_column: true
  cross_sectional/panel_b/variant:
    description: Example variant panel
    resolutions: [1d]
    status: active
    asset_column: true
  macro:
    description: Macro package
    resolutions: [1d]
    status: active
features:
  1d/btc:
    data_path: features/1d/btc/data.parquet
    status: active
  1d/btc/slice-a:
    data_path: features/1d/btc/slice-a/data.parquet
    status: active
  1m/btc/slice-b:
    data_path: features/1m/btc/slice-b/data.parquet
    status: active
  1d/cross_sectional/composite:
    data_path: features/1d/cross_sectional/composite/data.parquet
    status: active
  1d/cross_sectional/panel_b:
    data_path: features/1d/cross_sectional/panel_b/data.parquet
    status: active
  1d/cross_sectional/panel_b/variant:
    data_path: features/1d/cross_sectional/panel_b/variant/data.parquet
    status: active
  1d/macro:
    data_path: features/1d/macro/data.parquet
    status: active
""".strip(),
        encoding="utf-8",
    )

    set_db_root(db_root)

    response = client.get("/api/catalog/logical")
    assert response.status_code == 200
    feature_items = {item["id"]: item for item in response.json()["items"] if item["kind"] == "feature_set"}

    assert list(feature_items) == [
        "feature_set:btc",
        "feature_set:cross_sectional/composite",
        "feature_set:macro",
        "feature_set:cross_sectional/panel_b",
    ]
    assert all(item["resolutions"] for item in feature_items.values())
    panel_b = feature_items["feature_set:cross_sectional/panel_b"]
    assert panel_b["category_path"] == "cross_sectional/panel_b"
    assert panel_b["label"] == "Example Panel B"
    assert panel_b["domain"] == "panel_b"
    assert panel_b["asset_column"] is True
    # A preset published beside the canonical panel is a selectable option of the
    # same family, not a separate item and not a dropped one.
    assert {option["version"]: option["path"] for option in panel_b["resolutions"]} == {
        "latest": "1d/cross_sectional/panel_b/data.parquet",
        "variant": "1d/cross_sectional/panel_b/variant/data.parquet",
    }
    assert all(option["exists"] for option in panel_b["resolutions"])
    assert feature_items["feature_set:btc"]["label"] == "BTC"
    # Every registered output under the family is an option, whatever its label
    # looks like: engine versions, named slices, and other resolutions alike.
    assert {
        (option["resolution"], option["version"]): option["path"]
        for option in feature_items["feature_set:btc"]["resolutions"]
    } == {
        ("1d", "latest"): "1d/btc/data.parquet",
        ("1d", "slice-a"): "1d/btc/slice-a/data.parquet",
        ("1m", "slice-b"): "1m/btc/slice-b/data.parquet",
    }


def test_browse_outside_root_rejected(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/browse/%2E%2E")
    assert response.status_code == 403


def test_preview_chart_single_series(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/chart/raw/1d/index/btc.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["x_column"] == "timestamp"
    assert payload["selected_y_column"] == "close"
    assert payload["selected_entity_column"] is None
    assert payload["points_total"] == 4
    assert len(payload["series"]) == 4


def test_preview_chart_tall_table_defaults_to_one_entity(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/chart/raw/1d/custom/equities.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["selected_y_column"] == "close"
    assert payload["selected_entity_column"] == "symbol"
    assert payload["selected_entity_value"] == "A"
    assert payload["has_repeated_timestamps"] is True
    assert payload["points_total"] == 3
    assert [point["y"] for point in payload["series"]] == [11.0, 12.0, 13.0]


@pytest.mark.parametrize(
    ("filename", "x_column", "timestamps", "dtype"),
    [
        ("epoch_ms.parquet", "time", [1609459200000, 1609462800000, 1609466400000], pl.Int64),
        ("epoch_seconds.parquet", "timestamp", [1609459200, 1609462800, 1609466400], pl.UInt32),
        (
            "epoch_microseconds.parquet",
            "datetime",
            [1609459200000000, 1609462800000000, 1609466400000000],
            pl.Int64,
        ),
        (
            "epoch_nanoseconds.parquet",
            "date",
            [1609459200000000000, 1609462800000000000, 1609466400000000000],
            pl.Int64,
        ),
    ],
)
def test_preview_chart_recognizes_named_epoch_columns(
    client,
    set_db_root,
    catalog_db_root,
    filename,
    x_column,
    timestamps,
    dtype,
):
    path = f"raw/1d/custom/{filename}"
    pl.DataFrame(
        {
            x_column: pl.Series(timestamps, dtype=dtype),
            "value": [1.0, 2.0, 3.0],
        }
    ).write_parquet(catalog_db_root / "data" / path)
    set_db_root(catalog_db_root)

    response = client.get(f"/api/catalog/chart/{path}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["x_column"] == x_column
    assert x_column not in payload["y_columns"]
    assert payload["series"][0]["x"].startswith("2021-01-01T00:00:00")


def test_preview_chart_prefers_reporting_period_over_snapshot_date(
    client,
    set_db_root,
    catalog_db_root,
):
    path = "raw/1d/custom/fundamentals.parquet"
    pl.DataFrame(
        {
            "snapshot_date": ["2024-01-02", "2024-01-02", "2024-01-02"],
            "period_end": [
                "2022-12-31T00:00:00+00:00",
                "2023-12-31T00:00:00+00:00",
                "2024-12-31T00:00:00+00:00",
            ],
            "value": [1.0, 2.0, 3.0],
        }
    ).write_parquet(catalog_db_root / "data" / path)
    set_db_root(catalog_db_root)

    response = client.get(f"/api/catalog/chart/{path}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["x_column"] == "period_end"
    assert payload["points_total"] == 3
    assert payload["series"][0]["x"].startswith("2022-12-31T00:00:00")


def test_preview_chart_uses_snapshot_date_as_temporal_fallback(
    client,
    set_db_root,
    catalog_db_root,
):
    path = "raw/1d/custom/snapshots.parquet"
    pl.DataFrame(
        {
            "snapshot_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "value": [1.0, 2.0, 3.0],
        }
    ).write_parquet(catalog_db_root / "data" / path)
    set_db_root(catalog_db_root)

    response = client.get(f"/api/catalog/chart/{path}")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["x_column"] == "snapshot_date"
    assert payload["points_total"] == 3


def test_preview_chart_values_supports_query(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/chart-values/raw/1d/custom/equities.parquet?entity_column=symbol&query=b")
    assert response.status_code == 200

    payload = response.json()
    assert payload["entity_column"] == "symbol"
    assert payload["total_values"] == 1
    assert payload["values"] == ["B"]


def test_preview_chart_bundle_multiple_axes_and_cells(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.post(
        "/api/catalog/chart-bundle/raw/1d/custom/equities.parquet",
        json={
            "charts": [
                {
                    "chart_id": "prices",
                    "series": [
                        {"metric": "open", "axis": "left"},
                        {"metric": "close", "axis": "right"},
                    ],
                },
                {
                    "chart_id": "volume",
                    "series": [
                        {"metric": "volume", "axis": "left"},
                    ],
                },
            ]
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["selected_entity_column"] == "symbol"
    assert payload["selected_entity_value"] == "A"
    assert payload["points_total"] == 3
    assert payload["points_returned"] == 3

    charts = {chart["chart_id"]: chart for chart in payload["charts"]}
    assert set(charts) == {"prices", "volume"}

    price_series = {series["metric"]: series for series in charts["prices"]["series"]}
    assert set(price_series) == {"open", "close"}
    assert price_series["open"]["axis"] == "left"
    assert price_series["close"]["axis"] == "right"
    assert [point["y"] for point in price_series["open"]["points"]] == [10.0, 11.0, 12.0]
    assert [point["y"] for point in price_series["close"]["points"]] == [11.0, 12.0, 13.0]

    volume_series = charts["volume"]["series"]
    assert len(volume_series) == 1
    assert volume_series[0]["metric"] == "volume"
    assert volume_series[0]["axis"] == "left"
    assert [point["y"] for point in volume_series[0]["points"]] == [1000, 1200, 1300]


def test_profile_parquet_features_infers_families_and_filters(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get(
        "/api/catalog/profile/raw/1d/custom/equities.parquet?query=volume&family=flow_liquidity&sort=name&page_size=10"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "raw/1d/custom/equities.parquet"
    assert payload["entity_columns"] == ["symbol"]
    assert payload["feature_columns"] >= 5
    assert payload["total_features"] == 1
    assert payload["features"][0]["name"] == "volume"
    assert payload["features"][0]["family"] == "flow_liquidity"
    assert payload["features"][0]["coverage"] == 1.0
    assert payload["features"][0]["sparkline"]


def test_profile_parquet_features_supports_entity_filter(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get(
        "/api/catalog/profile/raw/1d/custom/equities.parquet?entity_column=symbol&entity_value=B&query=close"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["total_rows"] == 2
    assert payload["selected_entity_column"] == "symbol"
    assert payload["selected_entity_value"] == "B"
    assert payload["features"][0]["name"] == "close"
    assert payload["features"][0]["non_null_count"] == 2


def test_profile_parquet_features_uses_epoch_time_as_the_x_axis(
    client,
    set_db_root,
    catalog_db_root,
):
    pl.DataFrame(
        {
            "time": [1609459200000, 1609462800000, 1609466400000],
            "value": [1.0, 2.0, 3.0],
        }
    ).write_parquet(catalog_db_root / "data" / "raw/1d/custom/epoch_ms.parquet")
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/profile/raw/1d/custom/epoch_ms.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["x_column"] == "time"
    assert payload["feature_columns"] == 1
    assert payload["features"][0]["name"] == "value"
    assert payload["features"][0]["sparkline"][0]["x"].startswith("2021-01-01T00:00:00")


def test_profile_parquet_feature_detail_returns_histogram_and_extremes(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/profile-detail/raw/1d/custom/equities.parquet?column=funding_rate")
    assert response.status_code == 200

    payload = response.json()
    assert payload["column"] == "funding_rate"
    assert payload["family"] == "carry_funding"
    assert payload["histogram"]
    assert payload["sparkline"]
    assert payload["latest_timestamp"] == "2024-01-03T00:00:00"
    assert payload["latest_top"][0]["entity"] == "A"


def test_profile_parquet_rejects_non_parquet(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/profile/raw/1d/macro/README.md")
    assert response.status_code == 400


def test_profile_parquet_rejects_outside_root(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/profile/%2E%2E")
    assert response.status_code == 403


def test_preview_chart_bundle_rejects_unknown_metric(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.post(
        "/api/catalog/chart-bundle/raw/1d/index/btc.parquet",
        json={
            "charts": [
                {
                    "chart_id": "main",
                    "series": [{"metric": "nope", "axis": "left"}],
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "invalid metric" in response.json()["detail"].lower()


def test_preview_chart_non_chartable_dataset(client, set_db_root, catalog_db_root):
    set_db_root(catalog_db_root)

    response = client.get("/api/catalog/chart/raw/1d/misc/non_chartable.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is False
    assert "no temporal column" in payload["reason"].lower()
    assert payload["series"] == []
