"""Tests for features API endpoints."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from features.blocks import FeatureBlocks


@pytest.fixture
def features_db_root():
    """Create a temporary db root with canonical latest-state feature datasets."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_root = Path(tmp_dir)

        macro_dir = db_root / "features" / "1d" / "macro"
        macro_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(3)],
                "feature_a": [0.1, 0.2, 0.3],
                "feature_b": [1.0, 0.8, 0.6],
            }
        ).write_parquet(macro_dir / "data.parquet")
        (macro_dir / "meta.yaml").write_text("owner: macro\n")

        panel_dir = db_root / "features" / "1d" / "example" / "panel"
        panel_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "bid_imbalance": [0.25, 0.31],
                "ask_imbalance": [0.75, 0.69],
                "spread": [0.001, 0.0012],
            }
        ).write_parquet(panel_dir / "data.parquet")
        (panel_dir / "meta.yaml").write_text("source: example\n")
        (panel_dir / "README.md").write_text("# Example panel\n\nFeature notes.\n")
        (panel_dir / "analysis_summary.json").write_text(json.dumps({"feature_count": 3}) + "\n")
        (panel_dir / "analysis_manifest.yaml").write_text("name: feature_analysis\n")
        pl.DataFrame(
            {
                "row_index": [0, 0, 1, 1],
                "column_index": [0, 1, 0, 1],
                "row_feature": ["bid_imbalance", "bid_imbalance", "ask_imbalance", "ask_imbalance"],
                "column_feature": ["bid_imbalance", "ask_imbalance", "bid_imbalance", "ask_imbalance"],
                "correlation": [1.0, -0.5, -0.5, 1.0],
                "abs_correlation": [1.0, 0.5, 0.5, 1.0],
                "row_cluster_id": [1, 1, 2, 2],
                "column_cluster_id": [1, 2, 1, 2],
                "row_is_representative": [True, True, False, False],
                "column_is_representative": [True, False, True, False],
            }
        ).write_parquet(panel_dir / "analysis_cluster_heatmap.parquet")
        pl.DataFrame(
            {
                "feature": ["bid_imbalance", "bid_imbalance", "ask_imbalance", "ask_imbalance"],
                "horizon": [1, 5, 1, 5],
                "mean_oriented_ic": [0.2, 0.4, -0.1, 0.3],
                "mean_validation_ic": [0.2, 0.4, -0.1, 0.3],
                "positive_fold_rate": [0.8, 0.9, 0.4, 0.7],
                "valid_folds": [5, 5, 5, 5],
            }
        ).write_parquet(panel_dir / "analysis_horizon_ic_matrix.parquet")
        (panel_dir / "analysis_correlation_heatmap.png").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        )

        xs_dir = db_root / "features" / "1d" / "cross_sectional" / "sample"
        xs_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "timestamp": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 2),
                ],
                "asset": ["BTC", "ETH", "BTC", "ETH"],
                "feature_a": [0.1, 0.2, 0.15, 0.22],
                "feature_b": [1.0, 0.8, 1.1, 0.75],
                "funding_rate": [0.001, -0.001, 0.002, -0.002],
                "dollar_volume": [10_000.0, 8_000.0, 12_000.0, 7_500.0],
                "market_cap_usd": [100_000.0, 75_000.0, 110_000.0, 72_000.0],
            }
        ).write_parquet(xs_dir / "data.parquet")
        (xs_dir / "meta.yaml").write_text("source: xs\n")

        # Single-name panel: one asset, a late-starting column, and both
        # publication sidecars (per-column meta and a coordinator run report).
        panel_dir = db_root / "features" / "1d" / "cross_sectional" / "example" / "panel"
        panel_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(4)],
                "asset": ["AAA", "AAA", "AAA", "AAA"],
                "close": [10.0, 11.0, 12.0, 13.0],
                "roa": [None, None, 0.5, 0.6],
                "short_interest": [None, None, None, None],
            }
        ).write_parquet(panel_dir / "data.parquet")
        (panel_dir / "meta.yaml").write_text(
            """
name: cross_sectional_example_panel
description: Example cross-sectional panel
created_at: '2024-01-04T00:00:00+00:00'
created_by: example_refresh
category: cross_sectional/example/panel
as_of:
  decision_lag_days: 1
columns:
  close:
    formula: split-adjusted close from the derived price panel
    unit: usd_per_share
    dependencies:
    - data/derived/1d/equities/example/price_panel.parquet
    coverage:
      non_null_rows: 4
      first_non_null: '2024-01-01'
      last_non_null: '2024-01-04'
      by_asset:
        AAA:
          non_null_rows: 4
  roa:
    formula: net income TTM / total assets
    unit: ratio
    dependencies:
    - data/derived/1d/equities/fundamentals.parquet
    coverage:
      non_null_rows: 2
      first_non_null: '2024-01-03'
      last_non_null: '2024-01-04'
freshness:
  example_equities/price_panel:
    path: db/data/derived/1d/equities/example/price_panel.parquet
    present: true
    captured_at: '2024-01-04T00:00:00+00:00'
    min_available: '2020-01-02'
    max_available: '2024-01-04'
owed:
  owed: example panel must be re-materialized
  reason: the panel predates a newer source
  columns_that_will_change:
  - market_cap
  columns_that_will_be_added:
  - new_column
  columns_unchanged:
  - close
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (panel_dir / "refresh_report.json").write_text(
            json.dumps(
                {
                    "generated_at": "2024-01-04T00:00:00+00:00",
                    "completed_at": "2024-01-04T00:02:00+00:00",
                    "mode": "incremental",
                    "sources": [
                        {
                            "id": "prices_source",
                            "required": True,
                            "driver": "backfill",
                            "stage": 0,
                            "description": "Grouped daily OHLCV bars",
                            "status": "UPDATED",
                            "driver_outcome": {"duration_seconds": 3.0, "skipped_reason": None, "error": None},
                            "coverage_after": {
                                "rows_scoped": 1200,
                                "min_date": "2020-01-02",
                                "max_date": "2024-01-04",
                            },
                            "duplicates_added": 0,
                            "conflicts_added": 1,
                            "missing_session_count": 3,
                            "rewrote_files": True,
                            "note": "59 new rows",
                        },
                        {
                            "id": "short_interest_source",
                            "required": False,
                            "driver": "bulk_capture",
                            "stage": 0,
                            "description": "Semi-monthly short interest",
                            "status": "UNAVAILABLE",
                            "driver_outcome": {
                                "duration_seconds": 0.0,
                                "skipped_reason": "The landed capture holds no AAA rows",
                                "error": None,
                            },
                            "coverage_after": {"rows_scoped": 0, "min_date": None, "max_date": None},
                            "duplicates_added": 0,
                            "rewrote_files": False,
                        },
                    ],
                    "raw_duplicates": {"raw_total": 377},
                    "publish": {
                        "diagnostics": {
                            "example_warnings": 2,
                            "example_rejections": 1,
                            "example_rejection_examples": [{"asset": "AAA"}],
                            "example_flag": True,
                        },
                        "gate_open": True,
                        "gate_reason": None,
                        "published": True,
                        "preset": "panel",
                        "rows": 4,
                        "columns": 5,
                        "assets": ["AAA"],
                        "start": "2024-01-01 00:00:00",
                        "end": "2024-01-04 00:00:00",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        yield db_root


def test_list_features_includes_nested_paths(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features")
    assert response.status_code == 200

    payload = response.json()
    resolution = next(item for item in payload if item["resolution"] == "1d")
    category_map = {
        category["category_path"]: category["versions"]
        for category in resolution["categories"]
    }

    assert "macro" in category_map
    assert "example/panel" in category_map
    assert category_map["example/panel"] == ["latest"]


def test_list_resolution_features(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/1d")
    assert response.status_code == 200

    payload = response.json()
    category_paths = {item["category_path"] for item in payload}
    assert "macro" in category_paths
    assert "example/panel" in category_paths


def test_get_feature_dataset_nested_category(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/datasets/features/query/1d/example/panel/data.parquet?limit=1"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel/data.parquet"
    assert payload["total_rows"] == 2
    assert payload["returned_rows"] == 1
    assert len(payload["data"]) == 1


def test_browse_feature_root(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/browser")
    assert response.status_code == 200

    payload = response.json()
    names = {item["name"] for item in payload["items"]}
    assert "1d" in names


def test_browse_feature_directory(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/browser/1d/example/panel")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel"
    item_names = {item["name"] for item in payload["items"]}
    assert {"data.parquet", "README.md", "meta.yaml"} <= item_names
    assert "analysis_correlation_heatmap.png" not in item_names
    item_types = {item["name"]: item["type"] for item in payload["items"]}
    assert item_types["analysis_summary.json"] == "json"
    assert item_types["analysis_manifest.yaml"] == "yaml"
    assert item_types["analysis_cluster_heatmap.parquet"] == "parquet"


def test_preview_feature_parquet_with_pagination(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/datasets/features/preview/1d/macro/data.parquet?page=2&page_size=2"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/macro/data.parquet"
    assert payload["total_rows"] == 3
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    assert payload["total_pages"] == 2
    assert payload["has_prev"] is True
    assert payload["has_next"] is False
    assert len(payload["rows"]) == 1


def test_preview_feature_markdown(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/markdown/1d/example/panel/README.md")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel/README.md"
    assert payload["lines"] == 3
    assert "Example panel" in payload["content"]


def test_preview_feature_structured_file(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    json_response = client.get("/api/features/structured/1d/example/panel/analysis_summary.json")
    assert json_response.status_code == 200
    assert json_response.json()["content"]["feature_count"] == 3

    yaml_response = client.get("/api/features/structured/1d/example/panel/analysis_manifest.yaml")
    assert yaml_response.status_code == 200
    assert yaml_response.json()["content"]["name"] == "feature_analysis"


def test_preview_feature_structured_file_rejects_unsupported_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/structured/1d/example/panel/data.parquet")

    assert response.status_code == 400
    assert "Only JSON and YAML" in response.json()["detail"]


def test_feature_analysis_correlation_returns_compact_representative_arrays(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/analysis/correlation/1d/example/panel/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel/analysis_cluster_heatmap.parquet"
    assert payload["total_rows"] == 4
    assert payload["returned_cells"] == 1
    assert payload["dimension"] == 2
    assert payload["clusters"] == 2
    assert payload["representatives"] == 1
    assert payload["row_index"] == [0]
    assert payload["column_index"] == [0]
    assert payload["correlation"] == [1.0]
    assert payload["distribution"] == [
        {"key": "strong_negative", "label": "<= -0.70", "count": 0, "share": 0.0},
        {"key": "moderate_negative", "label": "-0.70 to -0.35", "count": 0, "share": 0.0},
        {"key": "weak", "label": "-0.35 to 0.35", "count": 0, "share": 0.0},
        {"key": "moderate_positive", "label": "0.35 to 0.70", "count": 0, "share": 0.0},
        {"key": "strong_positive", "label": ">= 0.70", "count": 0, "share": 0.0},
    ]
    assert payload["top_pairs"] == []


def test_feature_analysis_correlation_can_return_full_matrix(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/analysis/correlation/1d/example/panel/data.parquet?representatives_only=false"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["returned_cells"] == 4
    assert payload["correlation"] == [1.0, -0.5, -0.5, 1.0]
    assert payload["distribution"][1]["count"] == 2
    assert payload["top_pairs"] == [
        {
            "row_feature": "bid_imbalance",
            "column_feature": "ask_imbalance",
            "correlation": -0.5,
            "abs_correlation": 0.5,
            "row_cluster_id": 1,
            "column_cluster_id": 2,
        }
    ]


def test_feature_analysis_ic_returns_compact_top_feature_matrix(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/analysis/ic/1d/example/panel/data.parquet?max_features=1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel/analysis_horizon_ic_matrix.parquet"
    assert payload["total_rows"] == 4
    assert payload["total_features"] == 2
    assert payload["features"] == ["bid_imbalance"]
    assert payload["horizons"] == [1, 5]
    assert payload["feature_index"] == [0, 0]
    assert payload["horizon"] == [1, 5]
    assert payload["mean_oriented_ic"] == [0.2, 0.4]


def test_preview_feature_image_endpoint_is_removed(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/image/1d/example/panel/analysis_correlation_heatmap.png")

    assert response.status_code == 404


def test_feature_preview_schema(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/datasets/features/schema/1d/example/panel/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    column_names = {col["name"] for col in payload["schema"]}
    assert {"timestamp", "bid_imbalance", "ask_imbalance", "spread"} <= column_names


def test_get_feature_stats_nested_category(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/datasets/features/stats/1d/example/panel/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/example/panel/data.parquet"
    columns = [row["column"] for row in payload["data"]]
    assert "bid_imbalance" in columns
    assert "ask_imbalance" in columns


def test_get_feature_correlation_nested_category(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/1d/correlation?category_path=example/panel")
    assert response.status_code == 200

    payload = response.json()
    assert payload["category_path"] == "example/panel"
    assert payload["version"] == "latest"
    assert len(payload["columns"]) >= 2
    assert len(payload["matrix"]) == len(payload["columns"])


def test_feature_correlation_requires_category_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/1d/correlation")
    assert response.status_code == 400
    assert "category_path is required" in response.json()["detail"]


def test_feature_correlation_rejects_invalid_category_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/1d/correlation?category_path=../secrets")
    assert response.status_code == 400
    assert "invalid segments" in response.json()["detail"]


def test_feature_correlation_not_found(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/1d/correlation?category_path=example/missing")
    assert response.status_code == 404


def test_feature_browser_rejects_invalid_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/browser/%2E%2E")
    assert response.status_code == 403


def test_preview_feature_chart(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/chart/1d/example/panel/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["x_column"] == "timestamp"
    assert payload["selected_y_column"] == "bid_imbalance"
    assert payload["points_total"] == 2
    assert len(payload["series"]) == 2


def test_preview_feature_chart_values_for_tall_dataset(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/chart-values/1d/cross_sectional/sample/data.parquet?entity_column=asset"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["entity_column"] == "asset"
    assert payload["values"] == ["BTC", "ETH"]


def test_preview_feature_chart_bundle_multiple_cells(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.post(
        "/api/features/chart-bundle/1d/cross_sectional/sample/data.parquet",
        json={
            "entity_value": "ETH",
            "charts": [
                {
                    "chart_id": "alpha",
                    "series": [
                        {"metric": "feature_a", "axis": "left"},
                        {"metric": "feature_b", "axis": "right"},
                    ],
                },
                {
                    "chart_id": "beta",
                    "series": [
                        {"metric": "feature_b", "axis": "left"},
                    ],
                },
            ],
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert payload["selected_entity_column"] == "asset"
    assert payload["selected_entity_value"] == "ETH"
    assert payload["points_total"] == 2

    charts = {chart["chart_id"]: chart for chart in payload["charts"]}
    alpha_series = {series["metric"]: series for series in charts["alpha"]["series"]}
    assert [point["y"] for point in alpha_series["feature_a"]["points"]] == [0.2, 0.22]
    assert [point["y"] for point in alpha_series["feature_b"]["points"]] == [0.8, 0.75]
    assert alpha_series["feature_b"]["axis"] == "right"

    beta_series = charts["beta"]["series"]
    assert len(beta_series) == 1
    assert beta_series[0]["metric"] == "feature_b"
    assert [point["y"] for point in beta_series[0]["points"]] == [0.8, 0.75]


def test_preview_feature_chart_defaults_to_asset_series(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/chart/1d/cross_sectional/sample/data.parquet")
    assert response.status_code == 200

    payload = response.json()
    assert payload["selected_entity_column"] == "asset"
    assert payload["selected_entity_value"] == "BTC"
    assert payload["points_total"] == 2


def test_profile_feature_parquet_infers_families(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile/1d/cross_sectional/sample/data.parquet"
        "?family=carry_funding&sort=name"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "1d/cross_sectional/sample/data.parquet"
    assert payload["entity_columns"] == ["asset"]
    assert payload["total_features"] == 1
    assert payload["features"][0]["name"] == "funding_rate"
    assert payload["features"][0]["family"] == "carry_funding"


def test_profile_feature_parquet_supports_search_pagination_and_entity_filter(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile/1d/cross_sectional/sample/data.parquet"
        "?query=volume&page=1&page_size=1&entity_column=asset&entity_value=ETH"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["selected_entity_column"] == "asset"
    assert payload["selected_entity_value"] == "ETH"
    assert payload["total_rows"] == 2
    assert payload["page_size"] == 1
    assert payload["total_features"] == 1
    assert payload["features"][0]["name"] == "dollar_volume"
    assert payload["features"][0]["non_null_count"] == 2


def test_profile_feature_parquet_detail(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile-detail/1d/cross_sectional/sample/data.parquet"
        "?column=market_cap_usd"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["column"] == "market_cap_usd"
    assert payload["family"] == "supply_mcap"
    assert payload["histogram"]
    assert payload["latest_timestamp"] == "2024-01-02T00:00:00"
    assert payload["latest_top"][0]["entity"] == "BTC"


def test_profile_feature_parquet_rejects_invalid_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/profile/%2E%2E")
    assert response.status_code == 403


def test_preview_feature_chart_bundle_pushes_entity_filter_into_duckdb(
    client, set_db_root, features_db_root, monkeypatch
):
    """Row reads project only the chart columns and filter the entity inside data.query."""
    from db_api import dataset_charts

    captured = []
    real_query_parquet = dataset_charts.query_parquet

    def recording_query_parquet(query, **kwargs):
        captured.append(query)
        return real_query_parquet(query, **kwargs)

    monkeypatch.setattr(dataset_charts, "query_parquet", recording_query_parquet)
    set_db_root(features_db_root)

    response = client.post(
        "/api/features/chart-bundle/1d/cross_sectional/sample/data.parquet",
        json={
            "entity_value": "ETH",
            "charts": [{"chart_id": "alpha", "series": [{"metric": "feature_a", "axis": "left"}]}],
        },
    )
    assert response.status_code == 200
    assert response.json()["selected_entity_value"] == "ETH"

    assert len(captured) == 1
    query = captured[0]
    assert query.scope == "features"
    assert query.path == "1d/cross_sectional/sample/data.parquet"
    assert query.columns == ("timestamp", "feature_a")
    assert query.entity_column == "asset"
    assert query.entity_values == ("ETH",)
    assert query.limit is None


def test_preview_feature_chart_values_filters_and_pages(client, set_db_root, features_db_root):
    set_db_root(features_db_root)
    base = "/api/features/chart-values/1d/cross_sectional/sample/data.parquet?entity_column=asset"

    filtered = client.get(f"{base}&query=et")
    assert filtered.status_code == 200
    assert filtered.json()["total_values"] == 1
    assert filtered.json()["values"] == ["ETH"]

    paged = client.get(f"{base}&limit=1&offset=1")
    assert paged.status_code == 200
    assert paged.json()["total_values"] == 2
    assert paged.json()["values"] == ["ETH"]


def test_feature_chart_caches_refresh_when_parquet_is_rewritten(client, set_db_root, features_db_root):
    """Memoized chart metadata and selector values key on the file signature."""
    set_db_root(features_db_root)
    target_dir = features_db_root / "features" / "1d" / "cross_sectional" / "rewrite"
    target_dir.mkdir(parents=True)
    target = target_dir / "data.parquet"
    url = "/api/features/chart-values/1d/cross_sectional/rewrite/data.parquet?entity_column=asset"

    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1)],
            "asset": ["AAA", "BBB"],
            "close": [1.0, 2.0],
        }
    ).write_parquet(target)
    first = client.get(url)
    assert first.status_code == 200
    assert first.json()["values"] == ["AAA", "BBB"]

    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1)] * 3,
            "asset": ["AAA", "BBB", "CCC"],
            "close": [1.0, 2.0, 3.0],
        }
    ).write_parquet(target)
    second = client.get(url)
    assert second.status_code == 200
    assert second.json()["values"] == ["AAA", "BBB", "CCC"]


def test_preview_feature_chart_bundle_groups_metrics_into_families(
    client, set_db_root, features_db_root, monkeypatch
):
    set_db_root(features_db_root)
    blocks = FeatureBlocks(
        labels={"carry_funding": "Carry / funding", "liquidity": "Liquidity"},
        rules=(("carry_funding", ("funding_*",)), ("liquidity", ("dollar_volume", "market_cap_usd"))),
    )
    monkeypatch.setattr(
        "db_api.dataset_profile_common.family_feature_blocks",
        lambda category: blocks if category == "cross_sectional/sample" else None,
    )

    response = client.post(
        "/api/features/chart-bundle/1d/cross_sectional/sample/data.parquet",
        json={"charts": []},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["chartable"] is True
    assert set(payload["y_column_families"]) == set(payload["y_columns"])
    assert payload["y_column_families"]["funding_rate"] == "carry_funding"

    families = {family["id"]: family for family in payload["families"]}
    assert families["carry_funding"]["label"] == "Carry / funding"
    assert sum(family["count"] for family in payload["families"]) == len(payload["y_columns"])
    assert [family["id"] for family in payload["families"]] == [
        family_id
        # The family declares its blocks and their display order; undeclared columns are "other".
        for family_id in (*blocks.labels, "other")
        if family_id in families
    ]


# --------------------------------------------------------------------------- #
# Single-name panel: entity axis, coverage dates, publication sidecars
# --------------------------------------------------------------------------- #


def test_profile_feature_parquet_offers_the_entity_axis_of_a_single_name_panel(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile/1d/cross_sectional/example/panel/data.parquet"
        "?entity_column=asset&entity_value=AAA&sort=name"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["entity_columns"] == ["asset"]
    assert payload["selected_entity_column"] == "asset"
    assert payload["selected_entity_value"] == "AAA"
    assert payload["total_rows"] == 4


def test_profile_feature_parquet_reports_first_and_last_non_null_dates(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile/1d/cross_sectional/example/panel/data.parquet?sort=name"
    )
    assert response.status_code == 200

    features = {item["name"]: item for item in response.json()["features"]}
    assert features["close"]["first_non_null"] == "2024-01-01T00:00:00"
    assert features["close"]["last_non_null"] == "2024-01-04T00:00:00"
    # A column that starts late reports its own first observation, not the panel's.
    assert features["roa"]["first_non_null"] == "2024-01-03T00:00:00"
    assert features["roa"]["coverage"] == 0.5
    # An all-null column has no observation to bound.
    assert features["short_interest"]["first_non_null"] is None
    assert features["short_interest"]["last_non_null"] is None


def test_profile_feature_detail_reports_first_and_last_non_null_dates(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/profile-detail/1d/cross_sectional/example/panel/data.parquet?column=roa"
    )
    assert response.status_code == 200

    stats = response.json()["stats"]
    assert stats["first_non_null"] == "2024-01-03T00:00:00"
    assert stats["last_non_null"] == "2024-01-04T00:00:00"


def test_feature_panel_meta_exposes_the_per_column_contract(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/panel-meta/1d/cross_sectional/example/panel/data.parquet"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["present"] is True
    assert payload["category"] == "cross_sectional/example/panel"
    assert payload["created_by"] == "example_refresh"
    assert payload["as_of"]["decision_lag_days"] == 1
    columns = {item["name"]: item for item in payload["columns"]}
    assert columns["roa"]["formula"] == "net income TTM / total assets"
    assert columns["roa"]["unit"] == "ratio"
    assert columns["roa"]["dependencies"] == ["data/derived/1d/equities/fundamentals.parquet"]
    assert columns["roa"]["first_non_null"] == "2024-01-03"
    assert columns["close"]["by_asset"]["AAA"]["non_null_rows"] == 4
    assert payload["freshness"][0]["source"] == "example_equities/price_panel"
    assert payload["freshness"][0]["max_available"] == "2024-01-04"


def test_feature_panel_meta_surfaces_the_work_the_publication_still_owes(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/panel-meta/1d/cross_sectional/example/panel/data.parquet"
    )
    assert response.status_code == 200

    owed = response.json()["owed"]
    assert owed["summary"] == "example panel must be re-materialized"
    assert owed["reason"].startswith("the panel predates")
    assert owed["columns_that_will_change"] == ["market_cap"]
    assert owed["columns_that_will_be_added"] == ["new_column"]
    assert owed["columns_unchanged"] == ["close"]


def test_feature_panel_meta_omits_owed_when_the_publication_declares_none(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get("/api/features/panel-meta/1d/example/panel/data.parquet")
    assert response.status_code == 200
    assert response.json()["owed"] is None


def test_feature_panel_meta_reports_absence_without_failing(client, set_db_root, features_db_root):
    set_db_root(features_db_root)
    (features_db_root / "features" / "1d" / "example" / "panel" / "meta.yaml").unlink()

    response = client.get("/api/features/panel-meta/1d/example/panel/data.parquet")
    assert response.status_code == 200
    assert response.json() == {
        "path": "1d/example/panel/data.parquet",
        "category": "example/panel",
        "present": False,
        "columns": [],
        "freshness": [],
        "owed": None,
    }


def test_feature_run_report_lists_per_source_status(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/run-report/1d/cross_sectional/example/panel/data.parquet"
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["present"] is True
    assert payload["report_file"] == "refresh_report.json"
    assert payload["mode"] == "incremental"
    assert payload["publish"]["gate_open"] is True
    assert payload["publish"]["assets"] == ["AAA"]
    sources = {item["id"]: item for item in payload["sources"]}
    assert sources["prices_source"]["status"] == "UPDATED"
    assert sources["prices_source"]["rows"] == 1200
    assert sources["prices_source"]["coverage_start"] == "2020-01-02"
    assert sources["prices_source"]["reason"] == "59 new rows"
    assert sources["short_interest_source"]["required"] is False
    assert sources["short_interest_source"]["rows"] == 0
    assert sources["short_interest_source"]["coverage_start"] is None
    # An unavailable source explains itself with the driver's own reason.
    assert sources["short_interest_source"]["reason"] == "The landed capture holds no AAA rows"


def test_feature_run_report_totals_the_integrity_counters_of_the_run(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)

    response = client.get(
        "/api/features/run-report/1d/cross_sectional/example/panel/data.parquet"
    )
    assert response.status_code == 200

    payload = response.json()
    # A gap is reported per source and totalled, so the run answers "what is missing?" once.
    sources = {item["id"]: item for item in payload["sources"]}
    assert sources["prices_source"]["missing_sessions"] == 3
    assert sources["prices_source"]["conflicts_added"] == 1
    assert sources["short_interest_source"]["missing_sessions"] is None

    integrity = payload["integrity"]
    assert integrity["missing_session_total"] == 3
    assert integrity["sources_with_missing_sessions"] == {"prices_source": 3}
    assert integrity["conflicts_added"] == 1
    assert integrity["raw_duplicate_rows"] == 377
    # Every integer publish diagnostic is surfaced by name; lists and flags are not counters.
    assert integrity["diagnostics"] == {"example_warnings": 2, "example_rejections": 1}


def test_feature_run_report_reports_no_integrity_block_when_the_run_records_none(
    client, set_db_root, features_db_root
):
    set_db_root(features_db_root)
    report_path = (
        features_db_root
        / "features"
        / "1d"
        / "cross_sectional"
        / "example"
        / "panel"
        / "refresh_report.json"
    )
    report = json.loads(report_path.read_text())
    report.pop("raw_duplicates")
    report["publish"].pop("diagnostics")
    for entry in report["sources"]:
        entry.pop("missing_session_count", None)
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

    response = client.get(
        "/api/features/run-report/1d/cross_sectional/example/panel/data.parquet"
    )
    assert response.status_code == 200
    assert response.json()["integrity"] is None


def test_feature_run_report_reports_absence_without_failing(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    response = client.get("/api/features/run-report/1d/cross_sectional/sample/data.parquet")
    assert response.status_code == 200
    assert response.json()["present"] is False
    assert response.json()["sources"] == []


def test_feature_publication_sidecars_reject_a_non_panel_path(client, set_db_root, features_db_root):
    set_db_root(features_db_root)

    assert client.get("/api/features/panel-meta/1d/macro").status_code == 422
    assert client.get("/api/features/run-report/1d/macro").status_code == 422
