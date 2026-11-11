"""Independent hand-ledger acceptance through the single-asset HTTP endpoint.

USAGE: uv run pytest apps/api/tests/test_single_asset_independent.py -q
Expected dollar PnL and holdings are hand-computed, independent of the reader.
"""

import json
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from strategies.research_surface import publish_research_surface

# --------------------------------------------------------------------------- #
# Independent saved-run fixture
# --------------------------------------------------------------------------- #

URL = "/api/backtests/strategy-types/hand-ledger/versions/v000/single-asset"
NAV = [1000.0, 1040.0, 990.0, 921.05, 921.05]
PRICES = {
    "A": [10.0, 12.0, 9.0, 10.0, 11.0],
    "B": [20.0, 22.0, 18.0, 16.0, 18.0],
    "UNHELD": [None, None, 8.0, 9.0, 10.0],
}


def _declare_artifacts(run):
    names = ("scheduled_target_weights.parquet", "scheduled_net_returns.parquet")
    (run / "artifacts.json").write_text(json.dumps(dict.fromkeys(names)))


@pytest.fixture
def hand_ledger(tmp_path, set_db_root):
    set_db_root(tmp_path)
    times = [datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(5)]
    # $50 and -$50 PnL while long 50 A / short 25 B; reverse at the third mark.
    # Reversal leaves short 27.5 A / long 13.75 B, costing $6.975 per asset.
    price_pnl = [0.0, 50.0, -50.0, -55.0, 0.0]
    fees = [0.0, 10.0, 0.0, 13.95, 0.0]
    previous_nav = [1000.0, *NAV[:-1]]
    net = [(pnl - fee) / equity for pnl, fee, equity in zip(price_pnl, fees, previous_nav, strict=True)]
    publish_research_surface(
        tmp_path,
        strategy_type="hand-ledger",
        memory_version="v000",
        state="candidate",
        experiment="independent",
        run_id="hand-run",
        title="Independent hand ledger",
        summary="Two-bar rebalancing with fees and a position reversal.",
        benchmark={"id": "A", "label": "A"},
        performance=pl.DataFrame(
            {
                "date": [value.date() for value in times],
                "strategy_daily_return": net,
                "strategy_portfolio_value": [equity / 10 for equity in NAV],
                "benchmark_daily_return": [0.0] * 5,
                "benchmark_portfolio_value": [100.0] * 5,
            }
        ),
    )
    run = tmp_path / "research/strategies/hand-ledger/v000/independent/hand-run"
    (run / "config.json").write_text(
        json.dumps(
            {
                "initial_capital": 1000.0,
                "trade_cost_bps": 100.0,
                "rebalance_every_bars": 2,
            }
        )
    )
    pl.DataFrame({"timestamp": times, **PRICES}).write_parquet(run / "prices.parquet")
    pl.DataFrame(
        {
            "timestamp": times,
            "A": [0.5, 0.5, -0.25, -0.25, 0.99],
            "B": [-0.5, -0.5, 0.25, 0.25, -0.99],
            "UNHELD": [0.0] * 5,
            "CASH": [1.0] * 5,
        }
    ).write_parquet(run / "scheduled_target_weights.parquet")
    pl.DataFrame(
        {
            "timestamp": times,
            "equity": NAV,
            "benchmark_equity": [1000.0] * 5,
            "price_return": [pnl / equity for pnl, equity in zip(price_pnl, previous_nav, strict=True)],
            "cost_return": [fee / equity for fee, equity in zip(fees, previous_nav, strict=True)],
            "net_return": net,
            "funding_return": [0.0] * 5,
            "turnover": [fee / 0.01 / equity for fee, equity in zip(fees, previous_nav, strict=True)],
        }
    ).write_parquet(run / "scheduled_net_returns.parquet")
    _declare_artifacts(run)
    return run


# --------------------------------------------------------------------------- #
# Independent HTTP acceptance
# --------------------------------------------------------------------------- #


def test_hand_computed_contribution_weights_gaps_and_terminal_mark(client, hand_ledger):
    expected_contribution = {
        "A": [0.0, 9.5, -5.5, -8.9475, -11.6975],
        "B": [0.0, -5.5, 4.5, 1.0525, 3.8025],
        "UNHELD": [0.0] * 5,
    }
    expected_marked_dollars = {
        "A": [0.0, 600.0, 450.0, -275.0, -302.5],
        "B": [0.0, -550.0, -450.0, 220.0, 247.5],
        "UNHELD": [0.0] * 5,
    }
    aggregate = [0.0] * 5
    for asset in expected_contribution:
        response = client.get(URL, params={"asset": asset})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["available"] is True
        assert body["run_id"] == "hand-run"
        assert body["asset"] == asset
        assert body["assets"] == ["A", "B", "UNHELD"]
        assert body["ever_held"] is (asset != "UNHELD")
        rows = body["data"]
        assert len(rows) == 5
        assert [row["price"] for row in rows] == PRICES[asset]
        assert [row["cumulative_contribution_pp"] for row in rows] == pytest.approx(
            expected_contribution[asset], abs=1e-12
        )
        assert [row["weight_percent"] for row in rows] == pytest.approx(
            [dollars / equity * 100 for dollars, equity in zip(expected_marked_dollars[asset], NAV, strict=True)],
            abs=1e-12,
        )
        for index, row in enumerate(rows):
            aggregate[index] += row["cumulative_contribution_pp"]
    assert aggregate == pytest.approx([(equity / 1000 - 1) * 100 for equity in NAV], abs=1e-12)


@pytest.mark.parametrize("asset", ["CASH", "MISSING", "../../config.json", 'A"; SELECT 1; --'])
def test_outside_membership_is_refused(client, hand_ledger, asset):
    assert client.get(URL, params={"asset": asset}).status_code == 404


def test_duplicate_price_timestamp_is_a_named_unavailable_response(client, hand_ledger):
    path = hand_ledger / "prices.parquet"
    prices = pl.read_parquet(path)
    pl.concat([prices, prices.head(1)]).write_parquet(path)
    _declare_artifacts(hand_ledger)
    response = client.get(URL, params={"asset": "A"})
    assert response.status_code == 409
    assert "unavailable" in response.json()["detail"]


def test_missing_held_mark_is_not_filled_or_liquidated(client, hand_ledger):
    path = hand_ledger / "prices.parquet"
    prices = pl.read_parquet(path).with_columns(pl.Series("A", [10.0, None, 9.0, 10.0, 11.0]))
    prices.write_parquet(path)
    _declare_artifacts(hand_ledger)
    assert client.get(URL, params={"asset": "A"}).status_code == 409


def test_projected_reads_select_only_the_requested_asset(client, hand_ledger, monkeypatch):
    import db_api.strategy_single_asset as reader

    original = reader.query_parquet
    projections = {}

    def query_and_record(query, **kwargs):
        projections[query.path.rsplit("/", 1)[-1]] = query.columns
        return original(query, **kwargs)

    monkeypatch.setattr(reader, "query_parquet", query_and_record)
    response = client.get(URL, params={"asset": "A"})
    assert response.status_code == 200
    assert projections["prices.parquet"] == ("timestamp", "A")
    assert projections["scheduled_target_weights.parquet"] == ("timestamp", "A")


@pytest.mark.parametrize("location", ["artifact", "ancestor"])
def test_symlinked_saved_evidence_is_refused(client, hand_ledger, location, tmp_path):
    if location == "artifact":
        original = hand_ledger / "prices.parquet"
        destination = tmp_path / "outside-prices.parquet"
    else:
        original = hand_ledger.parent
        destination = tmp_path / "outside-experiment"
    original.rename(destination)
    original.symlink_to(destination, target_is_directory=location == "ancestor")
    # Discovery may already remove a version whose selected manifest traverses a symlink.
    assert client.get(URL, params={"asset": "A"}).status_code in (404, 409)
