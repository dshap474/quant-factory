"""Research strategy-surface publication, validation, and discovery tests.

Usage: uv run pytest packages/strategies/tests/unit/test_research_surface.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
import json
from datetime import UTC, date, datetime

import polars as pl
import pytest
from strategies.research_surface import (
    canonical_metric,
    discover_invalidated_research_versions,
    discover_research_strategy_versions,
    discover_strategy_lifecycle_versions,
    discover_strategy_versions_with_research,
    load_research_baseline,
    load_research_surface,
    metric_definitions,
    publish_research_surface,
    research_display_state,
    select_research_baseline,
    validate_grid_summary,
)
from strategies.versioned import get_version_final_dir


def _performance() -> pl.DataFrame:
    strategy_returns = [0.01, -0.02, 0.03]
    benchmark_returns = [0.0, 0.01, -0.005]

    def values(returns: list[float]) -> list[float]:
        value = 100.0
        result = []
        for daily_return in returns:
            value *= 1.0 + daily_return
            result.append(value)
        return result

    return pl.DataFrame(
        {
            "date": [date(2024, 1, day) for day in range(1, 4)],
            "strategy_daily_return": strategy_returns,
            "strategy_portfolio_value": values(strategy_returns),
            "benchmark_daily_return": benchmark_returns,
            "benchmark_portfolio_value": values(benchmark_returns),
            "daily_turnover": [0.2, 0.3, 0.1],
        }
    )


def _pnl() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 2, 1, hour, tzinfo=UTC) for hour in range(3)],
            "cumulative_pnl_usd": [0.0, 2.5, -1.25],
        }
    )


def _comparison_pnl() -> pl.DataFrame:
    return _pnl().with_columns(pl.Series("benchmark_cumulative_pnl_usd", [0.0, 1.0, -4.0]))


def _publish(
    db_root,
    *,
    state="candidate",
    run_id="20240104T000000Z-run",
    memory_version="v002",
):
    return publish_research_surface(
        db_root,
        strategy_type="example-ranking-strategy",
        memory_version=memory_version,
        state=state,
        experiment="optimizer",
        run_id=run_id,
        performance=_performance(),
        title="v002 research performance",
        summary="Validated candidate performance against BTC.",
        benchmark={"id": "BTC", "label": "BTC buy & hold"},
        diagnostics=[{"key": "turnover", "label": "Turnover", "value": 0.2, "format": "number"}],
        gates=[
            {
                "name": "Sharpe",
                "requirement": ">= 1",
                "result": 1.2,
                "format": "number",
                "passed": True,
            }
        ],
        disclosures=["Research only."],
        published_at=datetime(2024, 1, 4, tzinfo=UTC),
    )


def _quality_manifest(**overrides):
    manifest = {
        "state": "candidate",
        "benchmark": {"id": "BTC", "label": "BTC buy & hold"},
        "metrics": {
            "strategy": {"sharpe": 1.2, "total_return": 0.5},
            "benchmark": {"sharpe": 0.8, "total_return": 0.4},
        },
        "gates": [{"passed": True}],
    }
    manifest.update(overrides)
    return manifest


def _grid_inputs(db_root) -> tuple[pl.DataFrame, dict[str, object]]:
    version_root = db_root / "research/strategies/example-ranking-strategy/v002"
    series_path = version_root / "optimizer/source/grid_daily.parquet"
    series_path.parent.mkdir(parents=True)
    config_ids = ["cell-a", "cell-b", "cell-c", "cell-d"]
    pl.DataFrame(
        {
            "config_id": [config_id for config_id in config_ids for _ in range(3)],
            "date": [date(2024, 1, day) for _ in config_ids for day in range(1, 4)],
            "daily_return": [0.01, -0.01, 0.02] * len(config_ids),
        }
    ).write_parquet(series_path)
    summary = pl.DataFrame(
        {
            "rank": [1, 2, 3, 4],
            "config_id": config_ids,
            "is_selected": [True, False, False, False],
            "is_control": [False, False, False, True],
            "penalty": [0.001, 0.002, 0.001, 0.002],
            "gross": [2.0, 2.0, 3.0, 3.0],
            "ir": [1.2, 1.1, 1.0, 0.9],
        }
    )
    grid = {
        "grid_schema_version": 1,
        "dimensions": [
            {"key": "penalty", "label": "Penalty", "format": "bps", "values": [0.001, 0.002]},
            {"key": "gross", "label": "Gross", "format": "number", "values": [2.0, 3.0]},
        ],
        "metrics": [
            {"key": "ir", "label": "IR", "format": "number", "higher_is_better": True},
        ],
        "selected_config_id": "cell-a",
        "control_config_id": "cell-d",
        "series": {
            "path": "optimizer/source/grid_daily.parquet",
            "config_id_column": "config_id",
            "date_column": "date",
            "return_column": "daily_return",
        },
    }
    return summary, grid


# --------------------------------------------------------------------------- #
# Publication and loading
# --------------------------------------------------------------------------- #


def test_research_display_state_uses_lifecycle_and_operator_selection_only():
    assert research_display_state(_quality_manifest()) == "candidate"
    assert research_display_state(_quality_manifest(state="rejected")) == "rejected"
    assert research_display_state(_quality_manifest(state="rejected", operator_baseline=True)) == "baseline"
    assert research_display_state(_quality_manifest(benchmark={"id": "control"})) == "candidate"
    assert research_display_state(_quality_manifest(gates=[{"passed": False}])) == "candidate"
    assert (
        research_display_state(
            _quality_manifest(
                metrics={
                    "strategy": {"sharpe": 0.99, "total_return": 0.5},
                    "benchmark": {"sharpe": 0.8, "total_return": 0.4},
                }
            )
        )
        == "candidate"
    )
    assert (
        research_display_state(
            _quality_manifest(
                metrics={
                    "strategy": {"sharpe": 1.2, "total_return": 0.4},
                    "benchmark": {"sharpe": 0.8, "total_return": 0.4},
                }
            )
        )
        == "candidate"
    )


def test_operator_baseline_pointer_selects_exactly_one_surface(tmp_path):
    _publish(tmp_path, state="rejected", memory_version="v002")
    _publish(
        tmp_path,
        state="candidate",
        memory_version="v003",
        run_id="20240105T000000Z-run",
    )

    pointer_path = select_research_baseline(
        tmp_path,
        strategy_type="example-ranking-strategy",
        memory_version="v002",
        selected_at=datetime(2024, 1, 6, tzinfo=UTC),
    )

    assert pointer_path == tmp_path / "research/strategies/example-ranking-strategy/baseline.json"
    pointer = load_research_baseline(tmp_path, "example-ranking-strategy")
    assert pointer is not None
    assert pointer["memory_version"] == "v002"
    assert pointer["selected_at"] == "2024-01-06T00:00:00+00:00"
    assert pointer["selected_manifest"] == "v002/optimizer/20240104T000000Z-run/surface/manifest.json"
    assert pointer["selected_run_id"] == "20240104T000000Z-run"
    _, selected = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    _, unselected = load_research_surface(tmp_path, "example-ranking-strategy", "v003")
    assert selected["operator_baseline"] is True
    assert research_display_state(selected) == "baseline"
    assert unselected["operator_baseline"] is False

    select_research_baseline(
        tmp_path,
        strategy_type="example-ranking-strategy",
        memory_version="v003",
        selected_at=datetime(2024, 1, 7, tzinfo=UTC),
    )
    _, formerly_selected = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    _, newly_selected = load_research_surface(tmp_path, "example-ranking-strategy", "v003")
    assert formerly_selected["operator_baseline"] is False
    assert newly_selected["operator_baseline"] is True


def test_publish_research_surface_round_trips_selected_run(tmp_path):
    pointer = _publish(tmp_path, state="rejected")

    loaded = load_research_surface(tmp_path, "example-ranking-strategy", "v002")

    assert pointer.name == "surface.json"
    assert loaded is not None
    frame, manifest = loaded
    assert frame.shape == (3, 6)
    assert manifest["state"] == "rejected"
    assert manifest["run_id"] == "20240104T000000Z-run"
    assert manifest["performance_unit"] == "usd"
    assert manifest["metrics"]["strategy"]["ending_value"] == pytest.approx(101.9494)


def test_publish_research_surface_round_trips_non_usd_index_unit(tmp_path):
    publish_research_surface(
        tmp_path,
        strategy_type="example-ranking-strategy",
        memory_version="v002",
        state="candidate",
        experiment="raw-index",
        run_id="20240104T000000Z-index",
        performance=_performance(),
        performance_unit="index",
        title="Raw capital index",
        summary="Normalized raw-unit capital, not USD.",
        benchmark={"id": "control", "label": "Control"},
    )

    loaded = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    assert loaded is not None
    assert loaded[1]["performance_unit"] == "index"


def test_publish_text_only_research_record_round_trips_without_performance(tmp_path):
    publish_research_surface(
        tmp_path,
        strategy_type="example-directional-strategy",
        memory_version="v001",
        state="rejected",
        experiment="example-record",
        run_id="20240101T000000Z-record",
        title="Example Strategy v001",
        summary="The example feature claim was falsified.",
        diagnostics=[{"key": "events", "label": "Evaluation events", "value": 500, "format": "number"}],
        gates=[
            {
                "name": "holdout_check",
                "requirement": "Candidate beats baseline",
                "result": -0.02,
                "format": "number",
                "passed": False,
            }
        ],
        disclosures=["No backtest was run."],
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    loaded = load_research_surface(tmp_path, "example-directional-strategy", "v001")

    assert loaded is not None
    frame, manifest = loaded
    assert frame.is_empty()
    assert manifest["performance"] is None
    assert manifest["metrics"] is None
    assert manifest["benchmark"] is None
    assert manifest["gates"][0]["passed"] is False
    assert not (
        tmp_path
        / "research/strategies/example-directional-strategy/v001/example-record"
        / "20240101T000000Z-record/surface/performance.parquet"
    ).exists()


def test_publish_pnl_research_surface_round_trips_chart(tmp_path):
    publish_research_surface(
        tmp_path,
        strategy_type="example-event-strategy",
        memory_version="v001",
        state="rejected",
        experiment="gate-record",
        run_id="pnl-surface-v1",
        title="Example Strategy v001",
        summary="Cumulative PnL on a $100 allocation.",
        pnl=_pnl(),
        pnl_metadata={
            "label": "v001 cumulative PnL",
            "allocation_usd": 100.0,
            "interpretation": "backtest",
        },
    )

    loaded = load_research_surface(tmp_path, "example-event-strategy", "v001")

    assert loaded is not None
    frame, manifest = loaded
    assert frame.columns == ["timestamp", "cumulative_pnl_usd"]
    assert frame["cumulative_pnl_usd"].to_list() == [0.0, 2.5, -1.25]
    assert manifest["performance"] is None
    assert manifest["metrics"] is None
    assert manifest["benchmark"] is None
    assert manifest["pnl"]["allocation_usd"] == 100.0
    assert manifest["pnl"]["interpretation"] == "backtest"


def test_publish_pnl_research_surface_round_trips_comparison(tmp_path):
    publish_research_surface(
        tmp_path,
        strategy_type="example-event-strategy",
        memory_version="v003",
        state="rejected",
        experiment="signal-record",
        run_id="comparison-surface-v1",
        title="Example Strategy v003",
        summary="Candidate and v001 cumulative PnL.",
        pnl=_comparison_pnl(),
        pnl_metadata={
            "label": "v003",
            "allocation_usd": 100.0,
            "interpretation": "backtest",
        },
        benchmark={"id": "v001", "label": "v001"},
    )

    loaded = load_research_surface(tmp_path, "example-event-strategy", "v003")

    assert loaded is not None
    frame, manifest = loaded
    assert frame.columns == [
        "timestamp",
        "cumulative_pnl_usd",
        "benchmark_cumulative_pnl_usd",
    ]
    assert frame["benchmark_cumulative_pnl_usd"].to_list() == [0.0, 1.0, -4.0]
    assert manifest["benchmark"] == {"id": "v001", "label": "v001"}


@pytest.mark.parametrize(
    ("frame", "benchmark"),
    [
        (_comparison_pnl(), None),
        (_pnl(), {"id": "v001", "label": "v001"}),
    ],
)
def test_publish_pnl_rejects_mismatched_comparison_metadata(tmp_path, frame, benchmark):
    with pytest.raises(ValueError, match="metadata and column must be supplied together"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-event-strategy",
            memory_version="v003",
            state="rejected",
            experiment="signal-record",
            run_id="invalid-comparison",
            title="Example Strategy v003",
            summary="Invalid comparison fixture.",
            pnl=frame,
            pnl_metadata={
                "label": "v003",
                "allocation_usd": 100.0,
                "interpretation": "backtest",
            },
            benchmark=benchmark,
        )


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (
            _pnl().with_columns(pl.col("cumulative_pnl_usd") + 1.0),
            "start at exactly zero",
        ),
        (
            _pnl().reverse(),
            "timestamps must be non-null, unique, and ascending",
        ),
        (
            _pnl().with_columns(
                pl.when(pl.int_range(pl.len()) == 1)
                .then(float("inf"))
                .otherwise(pl.col("cumulative_pnl_usd"))
                .alias("cumulative_pnl_usd")
            ),
            "PnL values must be finite",
        ),
    ],
)
def test_publish_pnl_rejects_invalid_chart_math(tmp_path, frame, message):
    with pytest.raises(ValueError, match=message):
        publish_research_surface(
            tmp_path,
            strategy_type="example-event-strategy",
            memory_version="v001",
            state="rejected",
            experiment="gate-record",
            run_id="invalid-pnl",
            title="Example Strategy v001",
            summary="Invalid PnL fixture.",
            pnl=frame,
            pnl_metadata={
                "label": "v001 cumulative PnL",
                "allocation_usd": 100.0,
                "interpretation": "backtest",
            },
        )


def test_publish_pnl_rejects_mixed_performance_contract(tmp_path):
    with pytest.raises(ValueError, match="cannot combine performance and PnL"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-event-strategy",
            memory_version="v001",
            state="rejected",
            experiment="gate-record",
            run_id="mixed-surface",
            title="Example Strategy v001",
            summary="Invalid mixed fixture.",
            performance=_performance(),
            benchmark={"id": "BTC", "label": "BTC buy & hold"},
            pnl=_pnl(),
            pnl_metadata={
                "label": "v001 cumulative PnL",
                "allocation_usd": 100.0,
                "interpretation": "backtest",
            },
        )


def test_text_only_research_record_rejects_performance_metadata(tmp_path):
    with pytest.raises(ValueError, match="cannot include performance metadata"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-directional-strategy",
            memory_version="v001",
            state="rejected",
            experiment="example-record",
            run_id="20240101T000000Z-record",
            title="Example Strategy v001",
            summary="The example feature claim was falsified.",
            benchmark={"id": "BTC", "label": "BTC buy & hold"},
        )


def test_publish_research_surface_rejects_incomplete_gate_display_metadata(tmp_path):
    with pytest.raises(ValueError, match="gate has invalid display metadata"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-directional-strategy",
            memory_version="v003",
            state="rejected",
            experiment="walk-forward",
            run_id="20240105T120000Z",
            title="Example Strategy v003",
            summary="Malformed gate fixture.",
            gates=[{"name": "example_gate", "requirement": "must pass", "passed": False}],
        )


def test_publish_research_surface_preserves_metric_override(tmp_path):
    override = {
        "strategy": {
            "sharpe": 1.234,
            "total_return": 0.25,
            "max_drawdown": -0.05,
            "ending_value": 125.0,
            "annualized_return": 0.12,
            "annualized_volatility": 0.10,
            "calmar": 2.4,
            "positive_days": 0.6,
            "sharpe_365": 1.234,
        },
        "benchmark": {
            "sharpe": None,
            "total_return": 0.10,
            "max_drawdown": 0.0,
            "ending_value": 110.0,
            "annualized_return": None,
            "annualized_volatility": 0.0,
            "calmar": None,
            "positive_days": 0.5,
        },
    }

    publish_research_surface(
        tmp_path,
        strategy_type="example-ranking-strategy",
        memory_version="v002",
        state="candidate",
        experiment="optimizer",
        run_id="20240104T000000Z-override",
        performance=_performance(),
        title="Metrics override",
        summary="Use verdict metrics without recomputing strategy statistics.",
        benchmark={"id": "BTC", "label": "BTC buy & hold"},
        metrics_override=override,
        published_at=datetime(2024, 1, 4, tzinfo=UTC),
    )

    loaded = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    assert loaded is not None
    _, manifest = loaded
    assert manifest["metrics"] == override


@pytest.mark.parametrize(
    "field",
    [
        "ending_value",
        "annualized_return",
        "annualized_volatility",
        "calmar",
        "positive_days",
    ],
)
@pytest.mark.parametrize("role", ["strategy", "benchmark"])
def test_incomplete_override_cannot_publish_or_replace_pointer(tmp_path, field, role):
    pointer = _publish(tmp_path)
    original = pointer.read_bytes()
    _, manifest = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    override = manifest["metrics"]
    del override[role][field]
    with pytest.raises(ValueError, match=rf"metrics\.{role} missing display fields: {field}"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-ranking-strategy",
            memory_version="v002",
            state="candidate",
            experiment="optimizer",
            run_id="bad-override",
            title="Incomplete display metrics",
            summary="Must not publish",
            performance=_performance(),
            benchmark={"id": "BTC", "label": "BTC"},
            metrics_override=override,
        )
    assert pointer.read_bytes() == original
    assert not (pointer.parent / "optimizer/bad-override").exists()


@pytest.mark.parametrize("value", [None, True, "0.1", float("nan"), float("inf")])
def test_override_rejects_invalid_required_number_before_writing(tmp_path, value):
    pointer = _publish(tmp_path)
    _, manifest = load_research_surface(tmp_path, "example-ranking-strategy", "v002")
    override = manifest["metrics"]
    override["strategy"]["annualized_volatility"] = value
    with pytest.raises(ValueError, match="annualized_volatility must be a finite number"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-ranking-strategy",
            memory_version="v002",
            state="candidate",
            experiment="optimizer",
            run_id="bad-number",
            title="Invalid display metric",
            summary="Must not publish",
            performance=_performance(),
            benchmark={"id": "BTC", "label": "BTC"},
            metrics_override=override,
        )
    assert not (pointer.parent / "optimizer/bad-number").exists()


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("nullable", [False, True])
def test_grid_undefined_metric_requires_explicit_nullable(tmp_path, value, nullable):
    summary, grid = _grid_inputs(tmp_path)
    grid["metrics"][0]["nullable"] = nullable
    summary = summary.with_columns(pl.Series("ir", [value, 1.1, 1.0, 0.9]))
    if nullable and value is None:
        assert validate_grid_summary(summary, grid)["ir"][0] is None
    else:
        with pytest.raises(ValueError, match="finite values"):
            validate_grid_summary(summary, grid)


def test_grid_nullable_metadata_requires_boolean(tmp_path):
    summary, grid = _grid_inputs(tmp_path)
    grid["metrics"][0]["nullable"] = "true"
    with pytest.raises(ValueError, match="nullable must be boolean"):
        validate_grid_summary(summary, grid)


def test_publish_research_surface_round_trips_grid(tmp_path):
    summary, grid = _grid_inputs(tmp_path)
    publish_research_surface(
        tmp_path,
        strategy_type="example-ranking-strategy",
        memory_version="v002",
        state="rejected",
        experiment="optimizer",
        run_id="20240104T000000Z-grid",
        performance=_performance(),
        title="Grid",
        summary="Static optimizer grid.",
        benchmark={"id": "BTC", "label": "BTC buy & hold"},
        grid_summary=summary,
        grid=grid,
    )

    loaded = load_research_surface(tmp_path, "example-ranking-strategy", "v002")

    assert loaded is not None
    _, manifest = loaded
    assert manifest["grid"]["summary"]["row_count"] == 4
    assert manifest["grid"]["series"]["row_count"] == 12
    assert manifest["grid"]["control_config_id"] == "cell-d"


def test_failed_publication_does_not_replace_selected_pointer(tmp_path):
    pointer = _publish(tmp_path)
    original = pointer.read_bytes()
    invalid = _performance().with_columns(pl.col("strategy_portfolio_value") + 1.0)

    with pytest.raises(ValueError, match="do not reconcile"):
        publish_research_surface(
            tmp_path,
            strategy_type="example-ranking-strategy",
            memory_version="v002",
            state="candidate",
            experiment="optimizer",
            run_id="20240105T000000Z-run",
            performance=invalid,
            title="Invalid",
            summary="Must fail before publication.",
            benchmark={"id": "BTC", "label": "BTC buy & hold"},
        )

    assert pointer.read_bytes() == original


def test_discovery_ignores_inconsistent_surface(tmp_path):
    pointer = _publish(tmp_path)
    pointer.write_text(pointer.read_text().replace("candidate", "rejected"))

    assert discover_research_strategy_versions(tmp_path) == []


def test_discovery_includes_text_only_research_record(tmp_path):
    publish_research_surface(
        tmp_path,
        strategy_type="example-directional-strategy",
        memory_version="v002",
        state="rejected",
        experiment="example-plan",
        run_id="20240101T000000Z-record",
        title="Example Strategy v002",
        summary="The plan was written but not run.",
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
    )

    rows = discover_research_strategy_versions(tmp_path)

    assert rows == [
        {
            "strategy_type": "example-directional-strategy",
            "memory_version": "v002",
            "total_runs": 1,
            "has_final": False,
            "best_sharpe": None,
            "best_return": None,
            "final_run_id": None,
            "latest_run": "2024-01-01T00:00:00+00:00",
            "state": "rejected",
            "display_state": "rejected",
            "operator_baseline": False,
            "source": "research",
            "selected_run_id": "20240101T000000Z-record",
            "experiment": "example-plan",
            "has_surface": True,
            "surface_rows": 0,
        }
    ]


def test_combined_discovery_surfaces_research_metadata(tmp_path):
    _publish(tmp_path, state="rejected")

    rows = discover_strategy_versions_with_research(tmp_path)

    assert len(rows) == 1
    assert rows[0]["memory_version"] == "v002"
    assert rows[0]["state"] == "rejected"
    assert rows[0]["display_state"] == "rejected"
    assert rows[0]["source"] == "research"
    assert rows[0]["selected_run_id"] == "20240104T000000Z-run"


def test_combined_discovery_includes_registered_versions_without_surfaces(tmp_path):
    _publish(tmp_path, state="rejected")
    lifecycle_root = tmp_path / "strategy-library"
    version_root = lifecycle_root / "example-ranking-strategy/optimization/v003"
    version_root.mkdir(parents=True)
    (version_root / "VERSION.toml").write_text('version = 3\nphase = "audited"\nstatus = "active"\n')

    lifecycle = discover_strategy_lifecycle_versions(["example-ranking-strategy"], strategy_library_root=lifecycle_root)
    rows = discover_strategy_versions_with_research(tmp_path, strategy_library_root=lifecycle_root)

    assert lifecycle[0]["memory_version"] == "v003"
    assert lifecycle[0]["lifecycle_phase"] == "audited"
    assert lifecycle[0]["lifecycle_status"] == "active"
    assert lifecycle[0]["has_surface"] is False
    assert [row["memory_version"] for row in rows] == ["v002", "v003"]
    assert rows[1]["state"] == "candidate"


def test_selected_surface_takes_precedence_over_lifecycle_record(tmp_path):
    _publish(tmp_path, state="rejected")
    lifecycle_root = tmp_path / "strategy-library"
    version_root = lifecycle_root / "example-ranking-strategy/optimization/v002"
    version_root.mkdir(parents=True)
    (version_root / "VERSION.toml").write_text('version = 2\nphase = "recorded"\nstatus = "supported"\n')

    rows = discover_strategy_versions_with_research(tmp_path, strategy_library_root=lifecycle_root)

    assert len(rows) == 1
    assert rows[0]["state"] == "rejected"
    assert rows[0]["has_surface"] is True
    assert "lifecycle_status" not in rows[0]


def test_combined_discovery_surfaces_latest_not_tested_version(tmp_path):
    version_root = tmp_path / "research/strategies/example-ranking-strategy/v002"
    older = version_root / "confirmation/20240104T000000Z-run/NOT_TESTED.json"
    latest = version_root / "confirmation/20240105T000000Z-run/NOT_TESTED.json"
    older.parent.mkdir(parents=True)
    latest.parent.mkdir(parents=True)
    older.write_text(
        '{"classification":"NOT TESTED","detected_at_utc":"2024-01-04T00:00:00Z",'
        '"reason":"old","scored_observations":0}'
    )
    latest.write_text(
        '{"classification":"NOT TESTED","detected_at_utc":"2024-01-05T00:00:00Z",'
        '"reason":"inputs changed","scored_observations":0}'
    )

    invalidated = discover_invalidated_research_versions(tmp_path)
    rows = discover_strategy_versions_with_research(tmp_path)

    assert invalidated == rows
    assert rows[0]["memory_version"] == "v002"
    assert rows[0]["state"] == "invalidated"
    assert rows[0]["display_state"] == "invalidated"
    assert rows[0]["selected_run_id"] == "20240105T000000Z-run"
    assert rows[0]["invalidation_reason"] == "inputs changed"
    assert rows[0]["scored_observations"] == 0


def test_complete_surface_takes_precedence_over_not_tested_attempt(tmp_path):
    _publish(tmp_path, state="rejected")
    disposition = (
        tmp_path / "research/strategies/example-ranking-strategy/v002/optimizer/20240105T000000Z-run/NOT_TESTED.json"
    )
    disposition.parent.mkdir(parents=True)
    disposition.write_text('{"classification":"NOT TESTED","reason":"later invalid attempt","scored_observations":0}')

    rows = discover_strategy_versions_with_research(tmp_path)

    assert len(rows) == 1
    assert rows[0]["state"] == "rejected"
    assert rows[0]["has_surface"] is True


def test_combined_discovery_prefers_promoted_canonical_version(tmp_path):
    _publish(tmp_path, state="rejected")
    final_dir = get_version_final_dir(tmp_path, "example-ranking-strategy", "v002")
    final_dir.mkdir(parents=True)
    (final_dir / "meta.json").write_text(
        json.dumps(
            {
                "run_id": "run-20240105-000000",
                "selected_run_id": "run-20240105-000000",
                "metrics": {"total_return": 0.2, "sharpe": 1.3},
                "created_at": "2024-01-05T00:00:00+00:00",
            }
        )
    )

    rows = discover_strategy_versions_with_research(tmp_path)

    assert len(rows) == 1
    assert rows[0]["state"] == "promoted"
    assert rows[0]["display_state"] == "promoted"
    assert rows[0]["source"] == "canonical"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("cagr", ("annualized_return", "higher")),
        ("sharpe_365", ("sharpe", "higher")),
        ("volatility_365", ("annualized_volatility", "lower")),
        ("max_drawdown", ("max_drawdown", "higher")),
        ("current_drawdown_days", ("current_drawdown_days", "lower")),
        ("fee_dollars", ("fee_dollars", "unranked")),
        ("mean_gross_exposure", ("mean_gross_exposure", "unranked")),
    ],
)
def test_canonical_metric_normalizes_aliases_and_direction(key, expected):
    assert canonical_metric(key) == expected


def test_metric_definitions_emit_each_alias_once():
    definitions = metric_definitions()
    aliases = [alias for item in definitions for alias in item["aliases"]]
    assert len(aliases) == len(set(aliases))
    assert {item["direction"] for item in definitions} == {"higher", "lower"}
    assert not {item["key"] for item in definitions} & set(aliases)
