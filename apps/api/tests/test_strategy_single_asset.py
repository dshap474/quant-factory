"""Known-answer and read-model tests for selected-run single-asset attribution.

USAGE::
    uv run pytest apps/api/tests/test_strategy_single_asset.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from db_api.strategy_single_asset import (
    SelectedLedger,
    SingleAssetIntegrityError,
    _build_asset_frame,
    load_single_asset_view,
)
from strategies.research_surface import publish_research_surface


def _ledger(*, cadence: int = 1, cost_bps: float = 100.0) -> SelectedLedger:
    return SelectedLedger(
        strategy_type="fixture-family",
        memory_version="v001",
        run_id="fixture-run",
        experiment="fixture",
        title="Fixture",
        benchmark_id="BTC",
        run_root=Path("/fixture"),
        target_name="effective_weights.parquet",
        returns_name="net_returns.parquet",
        performance_path="fixture/performance.parquet",
        asset_names=("BTC",),
        initial_capital=1_000.0,
        cost_bps=cost_bps,
        rebalance_every_bars=cadence,
    )


@pytest.fixture
def selected_ledger_root(tmp_path: Path) -> Path:
    strategy_type = "fixture-family"
    memory_version = "v001"
    experiment = "fixture"
    run_id = "20260910T000000Z-fixture"
    run_root = tmp_path / "research" / "strategies" / strategy_type / memory_version / experiment / run_id
    run_root.mkdir(parents=True)
    timestamps = [datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(3)]
    equity = [1_000.0, 1_035.0, 1_018.5]
    net_return = [0.0, 0.035, -16.5 / 1_035.0]
    price_return = [0.0, 0.05, 0.0]
    cost_return = [0.0, 0.015, 16.5 / 1_035.0]
    turnover = [0.0, 1.5, 1_650.0 / 1_035.0]

    pl.DataFrame(
        {
            "timestamp": timestamps,
            "BTC": [100.0, 110.0, 120.0],
            "SHORT": [10.0, 11.0, 12.0],
            "UNUSED": [2.0, 2.0, 2.0],
            "LATE": [None, None, 5.0],
        }
    ).write_parquet(run_root / "prices.parquet")
    pl.DataFrame(
        {
            "timestamp": timestamps,
            "BTC": [1.0, 0.0, 1.0],
            "SHORT": [-0.5, 0.0, -0.5],
            "UNUSED": [0.0, 0.0, 0.0],
            "LATE": [0.0, 0.0, 1.0],
            "CASH": [0.5, 1.0, 0.5],
        }
    ).write_parquet(run_root / "effective_weights.parquet")
    pl.DataFrame(
        {
            "equity": equity,
            "benchmark_equity": equity,
            "price_return": price_return,
            "funding_return": [0.0, 0.0, 0.0],
            "cost_return": cost_return,
            "net_return": net_return,
            "turnover": turnover,
            "timestamp": timestamps,
        }
    ).write_parquet(run_root / "net_returns.parquet")
    (run_root / "config.json").write_text(
        json.dumps(
            {
                "initial_capital": 1_000.0,
                "trade_cost_bps": 100.0,
                "rebalance_every_bars": 1,
            }
        )
    )
    performance = pl.DataFrame(
        {
            "date": [timestamp.date() for timestamp in timestamps],
            "strategy_daily_return": net_return,
            "strategy_portfolio_value": [value / 10.0 for value in equity],
            "benchmark_daily_return": net_return,
            "benchmark_portfolio_value": [value / 10.0 for value in equity],
        }
    )
    publish_research_surface(
        tmp_path,
        strategy_type=strategy_type,
        memory_version=memory_version,
        state="candidate",
        experiment=experiment,
        run_id=run_id,
        title="Fixture selected ledger",
        summary="Fixture",
        performance=performance,
        benchmark={"id": "BTC", "label": "BTC"},
        disclosures=(),
    )
    artifacts = dict.fromkeys(("effective_weights.parquet", "net_returns.parquet"))
    (run_root / "artifacts.json").write_text(json.dumps(artifacts))
    return tmp_path


# --------------------------------------------------------------------------- #
# Accounting tests
# --------------------------------------------------------------------------- #


def test_known_long_short_fees_exit_and_terminal_target() -> None:
    timestamps = [datetime(2026, 1, day, tzinfo=UTC) for day in range(1, 4)]
    returns = pl.DataFrame({"timestamp": timestamps, "equity": [1_000.0, 1_035.0, 1_018.5]})
    btc = _build_asset_frame(
        _ledger(),
        "BTC",
        pl.DataFrame({"timestamp": timestamps, "BTC": [1.0, 0.0, 1.0]}),
        pl.DataFrame({"timestamp": timestamps, "BTC": [100.0, 110.0, 120.0]}),
        returns,
    )
    short = _build_asset_frame(
        _ledger(),
        "SHORT",
        pl.DataFrame({"timestamp": timestamps, "SHORT": [-0.5, 0.0, -0.5]}),
        pl.DataFrame({"timestamp": timestamps, "SHORT": [10.0, 11.0, 12.0]}),
        returns,
    )

    assert btc["weight_percent"].to_list() == pytest.approx([0.0, 1_100 / 1_035 * 100, 0.0])
    assert btc["cumulative_contribution_pp"].to_list() == pytest.approx([0.0, 9.0, 7.9])
    assert short["cumulative_contribution_pp"].to_list() == pytest.approx([0.0, -5.5, -6.05])
    assert btc["cumulative_contribution_pp"][-1] + short["cumulative_contribution_pp"][-1] == pytest.approx(
        (1_018.5 / 1_000.0 - 1.0) * 100.0
    )


def test_weekly_quantity_drifts_and_missing_held_mark_is_rejected() -> None:
    timestamps = [datetime(2026, 1, day, tzinfo=UTC) for day in range(1, 4)]
    returns = pl.DataFrame({"timestamp": timestamps, "equity": [1_000.0, 1_050.0, 1_100.0]})
    targets = pl.DataFrame({"timestamp": timestamps, "BTC": [0.5, 0.5, -0.5]})
    prices = pl.DataFrame({"timestamp": timestamps, "BTC": [10.0, 11.0, 12.0]})
    frame = _build_asset_frame(_ledger(cadence=2, cost_bps=0.0), "BTC", targets, prices, returns)

    assert frame["weight_percent"].to_list() == pytest.approx([0.0, 550 / 1_050 * 100, 600 / 1_100 * 100])
    assert frame["cumulative_contribution_pp"].to_list() == pytest.approx([0.0, 5.0, 10.0])
    with pytest.raises(SingleAssetIntegrityError, match="held ending mark"):
        _build_asset_frame(
            _ledger(cadence=2, cost_bps=0.0),
            "BTC",
            targets,
            pl.DataFrame({"timestamp": timestamps, "BTC": [10.0, None, 12.0]}),
            returns,
        )


# --------------------------------------------------------------------------- #
# Read-model tests
# --------------------------------------------------------------------------- #


def test_selected_run_assets_prices_and_contributions(selected_ledger_root: Path) -> None:
    before = {path: path.read_bytes() for path in (selected_ledger_root / "research").rglob("*") if path.is_file()}
    payload = load_single_asset_view(
        selected_ledger_root,
        "fixture-family",
        "v001",
        asset="BTC",
        expected_run_id="20260910T000000Z-fixture",
    )

    assert payload["available"] is True
    assert payload["assets"] == ["BTC", "LATE", "SHORT", "UNUSED"]
    assert payload["asset"] == "BTC"
    assert payload["data"]["price"].to_list() == [100.0, 110.0, 120.0]
    assert payload["data"]["cumulative_contribution_pp"].to_list() == pytest.approx([0.0, 9.0, 7.9])
    after = {path: path.read_bytes() for path in before}
    assert after == before


def test_default_asset_unused_asset_and_unsafe_selection(selected_ledger_root: Path) -> None:
    default = load_single_asset_view(selected_ledger_root, "fixture-family", "v001")
    unused = load_single_asset_view(selected_ledger_root, "fixture-family", "v001", asset="UNUSED")

    assert default["asset"] == "BTC"
    assert unused["ever_held"] is False
    assert unused["ending_contribution_pp"] == 0.0
    with pytest.raises(ValueError, match="not in selected run"):
        load_single_asset_view(
            selected_ledger_root,
            "fixture-family",
            "v001",
            asset="../../config.json",
        )
    with pytest.raises(ValueError, match="not in selected run"):
        load_single_asset_view(selected_ledger_root, "fixture-family", "v001", asset="CASH")


def test_refuses_stale_identity(selected_ledger_root: Path) -> None:
    with pytest.raises(SingleAssetIntegrityError, match="selected run changed"):
        load_single_asset_view(
            selected_ledger_root,
            "fixture-family",
            "v001",
            expected_run_id="another-run",
        )


def test_preserves_late_listing_gap_with_bounded_output(selected_ledger_root: Path) -> None:
    payload = load_single_asset_view(
        selected_ledger_root,
        "fixture-family",
        "v001",
        asset="LATE",
        max_points=3,
    )

    assert payload["points_returned"] == 3
    assert payload["data"]["price"].to_list() == [None, None, 5.0]


def test_http_route_returns_selected_run_and_rejects_unknown_asset(
    selected_ledger_root: Path,
    client,
    set_db_root,
) -> None:
    set_db_root(selected_ledger_root)
    response = client.get(
        "/api/backtests/strategy-types/fixture-family/versions/v001/single-asset",
        params={"asset": "SHORT"},
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == "20260910T000000Z-fixture"
    assert response.json()["asset"] == "SHORT"
    refused = client.get(
        "/api/backtests/strategy-types/fixture-family/versions/v001/single-asset",
        params={"asset": "../SHORT"},
    )
    assert refused.status_code == 404
