"""Unit tests for StrategyWeights."""

from datetime import datetime

import polars as pl
import pytest

from strategies import ExecutionMode, ExecutionTiming, RebalanceMode, StrategyWeights


class TestStrategyWeights:
    """Tests for StrategyWeights class."""

    def test_valid_single_asset(self):
        """Test valid single-asset weights."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "BTC": [0.5, -0.3],
            "CASH": [0.5, 1.3],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        assert sw.n_assets == 1
        assert sw.n_timestamps == 2
        assert sw.assets == ["BTC"]

        # Should not raise
        sw.validate()

    def test_valid_multi_asset(self):
        """Test valid multi-asset weights."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "BTC": [0.2, 0.25],
            "ETH": [0.2, 0.15],
            "SOL": [-0.1, -0.15],
            "CASH": [0.7, 0.75],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH", "SOL"])

        assert sw.n_assets == 3
        assert sw.n_timestamps == 2

        # Should not raise
        sw.validate()

    def test_invalid_row_sums(self):
        """Test that validation fails when rows don't sum to 1.0."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.3],  # Sums to 0.8, not 1.0
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            sw.validate()

    def test_missing_timestamp_column(self):
        """Test that initialization fails without timestamp column."""
        weights_df = pl.DataFrame({
            "BTC": [0.5],
            "CASH": [0.5],
        })

        with pytest.raises(ValueError, match="timestamp"):
            StrategyWeights(weights=weights_df, assets=["BTC"])

    def test_missing_cash_column(self):
        """Test that initialization fails without cash column."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
        })

        with pytest.raises(ValueError, match="CASH"):
            StrategyWeights(weights=weights_df, assets=["BTC"])

    def test_missing_asset_column(self):
        """Test that initialization fails when asset column is missing."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "ETH": [0.5],  # BTC is missing
            "CASH": [0.5],
        })

        with pytest.raises(ValueError, match="BTC"):
            StrategyWeights(weights=weights_df, assets=["BTC"])

    def test_get_asset_exposure(self):
        """Test get_asset_exposure method."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "BTC": [0.5, 0.3],
            "CASH": [0.5, 0.7],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        exposure = sw.get_asset_exposure("BTC")
        assert exposure.to_list() == [0.5, 0.3]

    def test_get_gross_exposure(self):
        """Test get_gross_exposure method."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.3],
            "ETH": [-0.2],
            "CASH": [0.9],  # Sums to 1.0
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH"])

        gross = sw.get_gross_exposure()
        assert gross[0] == pytest.approx(0.5)  # |0.3| + |-0.2| = 0.5

    def test_get_net_exposure(self):
        """Test get_net_exposure method."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.3],
            "ETH": [-0.2],
            "CASH": [0.9],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH"])

        net = sw.get_net_exposure()
        assert net[0] == pytest.approx(0.1)  # 0.3 - 0.2 = 0.1

    def test_is_market_neutral_true(self):
        """Test is_market_neutral for balanced portfolio."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.25],
            "ETH": [-0.25],  # Net = 0
            "CASH": [1.0],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH"])

        assert sw.is_market_neutral() is True

    def test_is_market_neutral_false(self):
        """Test is_market_neutral for unbalanced portfolio."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "ETH": [-0.2],  # Net = 0.3
            "CASH": [0.7],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH"])

        assert sw.is_market_neutral() is False

    def test_summary(self):
        """Test summary method."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        summary = sw.summary()
        assert "StrategyWeights" in summary
        assert "BTC" in summary
        assert "n_timestamps=1" in summary

    def test_custom_cash_column(self):
        """Test using a custom cash column name."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "USD": [0.5],  # Custom cash column
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"], cash_col="USD")

        assert sw.cash_col == "USD"
        sw.validate()  # Should not raise

    def test_tolerance_validation(self):
        """Test that validation respects tolerance parameter."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.505],
            "CASH": [0.505],  # Sums to 1.01, within 0.02 tolerance
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        # Should fail with default tolerance (0.01)
        with pytest.raises(ValueError):
            sw.validate(tolerance=0.005)

        # Should pass with higher tolerance
        sw.validate(tolerance=0.02)

    def test_metadata(self):
        """Test metadata storage."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        })
        sw = StrategyWeights(
            weights=weights_df,
            assets=["BTC"],
            metadata={"source": "test", "version": 1},
        )

        assert sw.metadata["source"] == "test"
        assert sw.metadata["version"] == 1

    def test_default_execution_is_next_bar(self):
        """StrategyWeights defaults to the repo-wide safe next-bar contract."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC"])

        assert sw.execution.mode == ExecutionMode.NEXT_BAR
        assert sw.execution.derive_lag_bars() == 1

    def test_lagged_execution_requires_positive_lag(self):
        """lag_bars mode rejects zero lag."""
        with pytest.raises(ValueError, match="lag_bars execution requires lag_bars >= 1"):
            ExecutionTiming(mode=ExecutionMode.LAG_BARS, lag_bars=0)


class TestStrategyWeightsIO:
    """Tests for StrategyWeights I/O methods."""

    def test_save_and_load(self, tmp_path):
        """Test save and load roundtrip."""
        weights_df = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "BTC": [0.5, 0.3],
            "ETH": [0.2, 0.4],
            "CASH": [0.3, 0.3],
        })
        sw = StrategyWeights(weights=weights_df, assets=["BTC", "ETH"])

        # Save
        path = tmp_path / "weights.parquet"
        sw.save(path)
        assert path.exists()

        # Load
        loaded = StrategyWeights.from_parquet(path)
        assert loaded.n_assets == 2
        assert loaded.assets == ["BTC", "ETH"]
        assert loaded.weights.equals(weights_df)

    def test_partial_targets_limits_and_contract_roundtrip(self, tmp_path):
        timestamps = [datetime(2024, 1, 1), datetime(2024, 1, 2)]
        weights = pl.DataFrame({
            "timestamp": timestamps,
            "BTC": [None, 0.4],
            "ETH": [0.2, 0.1],
            "USD": [None, 0.5],
        })
        limits = pl.DataFrame({
            "timestamp": timestamps,
            "BTC": [0.0, None],
            "ETH": [-2.5, 3.0],
        })
        original = StrategyWeights(
            weights=weights,
            assets=["BTC", "ETH"],
            cash_col="USD",
            execution=ExecutionTiming.next_bar(rebalance_mode=RebalanceMode.FLAT_THEN_TARGET),
            metadata={"source": "test", "settings": [1, True, None]},
            quantity_limits=limits,
        )
        path = tmp_path / "weights.parquet"
        original.save(path)

        loaded = StrategyWeights.from_parquet(path)
        assert loaded.weights.equals(weights)
        assert loaded.quantity_limits is not None
        assert loaded.quantity_limits.equals(limits)
        assert loaded.assets == original.assets
        assert loaded.cash_col == "USD"
        assert loaded.execution == original.execution
        assert loaded.metadata == original.metadata

    def test_legacy_parquet_loads_with_defaults(self, tmp_path):
        path = tmp_path / "old.parquet"
        pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        }).write_parquet(path)
        loaded = StrategyWeights.from_parquet(path)
        assert loaded.assets == ["BTC"]
        assert loaded.execution.mode == ExecutionMode.NEXT_BAR
        assert loaded.metadata == {}
        assert loaded.quantity_limits is None

    def test_all_hold_and_all_unconstrained_columns_roundtrip(self, tmp_path):
        timestamp = datetime(2024, 1, 1)
        original = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [timestamp], "BTC": [None], "CASH": [None]}),
            assets=["BTC"],
            quantity_limits=pl.DataFrame({"timestamp": [timestamp], "BTC": [None]}),
        )
        path = tmp_path / "hold.parquet"
        original.save(path)
        loaded = StrategyWeights.from_parquet(path)
        assert loaded.weights.equals(original.weights)
        assert loaded.quantity_limits is not None
        assert loaded.quantity_limits.equals(original.quantity_limits)

    @pytest.mark.parametrize("target,cash", [(None, 1.0), (0.5, None)])
    def test_partial_cash_must_match_null_targets(self, target, cash):
        weights = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [target],
            "CASH": [cash],
        })
        with pytest.raises(ValueError, match="CASH must be null"):
            StrategyWeights(weights=weights, assets=["BTC"]).validate()

    def test_limits_must_align_and_be_finite(self):
        weights = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        })
        with pytest.raises(ValueError, match="align row-for-row"):
            StrategyWeights(
                weights=weights,
                assets=["BTC"],
                quantity_limits=pl.DataFrame({"timestamp": [datetime(2024, 1, 2)], "BTC": [1.0]}),
            )
        with pytest.raises(ValueError, match="finite"):
            StrategyWeights(
                weights=weights,
                assets=["BTC"],
                quantity_limits=pl.DataFrame({"timestamp": weights["timestamp"], "BTC": [float("inf")]}),
            ).validate()

    def test_identity_roundtrips_and_older_artifacts_load_without_it(self, tmp_path):
        weights = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "BTC": [0.5], "CASH": [0.5]})
        stamped = StrategyWeights(weights=weights, assets=["BTC"], strategy_id="demo", version="v001")
        path = tmp_path / "stamped.parquet"
        stamped.save(path)
        loaded = StrategyWeights.from_parquet(path)
        assert (loaded.strategy_id, loaded.version) == ("demo", "v001")

        unstamped = tmp_path / "unstamped.parquet"
        StrategyWeights(weights=weights, assets=["BTC"]).save(unstamped)
        assert (StrategyWeights.from_parquet(unstamped).strategy_id,
                StrategyWeights.from_parquet(unstamped).version) == (None, None)
        with pytest.raises(ValueError, match="non-empty string"):
            StrategyWeights(weights=weights, assets=["BTC"], strategy_id=" ")

    def test_slice_and_concat_preserve_the_contract(self):
        timestamps = [datetime(2024, 1, day) for day in (1, 2, 3)]
        full = StrategyWeights(
            weights=pl.DataFrame({"timestamp": timestamps, "BTC": [0.5, None, 0.2], "CASH": [0.5, None, 0.8]}),
            assets=["BTC"],
            metadata={"policy": "demo"},
            quantity_limits=pl.DataFrame({"timestamp": timestamps, "BTC": [None, 2.0, None]}),
            strategy_id="demo",
            version="v001",
        )
        parts = [full.slice(index, 1) for index in range(3)]
        assert parts[1].weights["BTC"].to_list() == [None]
        assert parts[1].quantity_limits is not None and parts[1].quantity_limits["BTC"].to_list() == [2.0]
        joined = StrategyWeights.concat(parts)
        assert joined.weights.equals(full.weights)
        assert joined.quantity_limits is not None and joined.quantity_limits.equals(full.quantity_limits)
        assert (joined.strategy_id, joined.version, joined.metadata) == ("demo", "v001", {"policy": "demo"})

        without_limits = StrategyWeights(weights=full.weights.slice(0, 1), assets=["BTC"],
                                         metadata={"policy": "demo"}, strategy_id="demo", version="v001")
        mixed = StrategyWeights.concat([without_limits, parts[1]])
        assert mixed.quantity_limits is not None and mixed.quantity_limits["BTC"].to_list() == [None, 2.0]
        other = StrategyWeights(weights=full.weights.slice(1, 1), assets=["BTC"],
                                metadata={"policy": "demo"}, strategy_id="demo", version="v002")
        with pytest.raises(ValueError, match="identity"):
            StrategyWeights.concat([without_limits, other])

    def test_metadata_rejects_lossy_json_values(self):
        weights = pl.DataFrame({
            "timestamp": [datetime(2024, 1, 1)],
            "BTC": [0.5],
            "CASH": [0.5],
        })
        with pytest.raises(ValueError, match="JSON-native"):
            StrategyWeights(weights=weights, assets=["BTC"], metadata={"tuple": (1, 2)}).validate()


class TestFromPortfolioWeights:
    """Tests for from_portfolio_weights conversion."""

    def test_scales_to_target_gross_exposure(self):
        """Test that weights are scaled to gross exposure = 1.0."""
        # Create mock PortfolioWeights with gross exposure = 2.0
        class MockPortfolioWeights:
            def __init__(self):
                self.long_assets = ["BTC", "ETH"]
                self.short_assets = ["SOL", "XRP"]

            def to_wide(self):
                return pl.DataFrame({
                    "timestamp": [datetime(2024, 1, 1)],
                    "BTC": [0.5],    # Long
                    "ETH": [0.5],    # Long
                    "SOL": [-0.5],   # Short
                    "XRP": [-0.5],   # Short
                })  # Gross = 2.0, Net = 0

        pw = MockPortfolioWeights()
        sw = StrategyWeights.from_portfolio_weights(pw, target_gross_exposure=1.0)

        # After scaling, gross should be 1.0
        gross = sw.get_gross_exposure()[0]
        assert gross == pytest.approx(1.0)

        # Net should still be 0
        net = sw.get_net_exposure()[0]
        assert net == pytest.approx(0.0, abs=0.001)

        # Individual weights should be scaled by 0.5
        assert sw.weights["BTC"][0] == pytest.approx(0.25)
        assert sw.weights["SOL"][0] == pytest.approx(-0.25)

        # CASH should be 1.0 for market-neutral
        assert sw.weights["CASH"][0] == pytest.approx(1.0)

    def test_default_preserves_gross_exposure(self):
        """Test that default behavior preserves optimizer gross exposure."""
        class MockPortfolioWeights:
            def __init__(self):
                self.long_assets = ["BTC", "ETH"]
                self.short_assets = ["SOL", "XRP"]

            def to_wide(self):
                return pl.DataFrame({
                    "timestamp": [datetime(2024, 1, 1)],
                    "BTC": [0.5],
                    "ETH": [0.5],
                    "SOL": [-0.5],
                    "XRP": [-0.5],
                })  # Gross = 2.0, Net = 0

        pw = MockPortfolioWeights()
        sw = StrategyWeights.from_portfolio_weights(pw)

        gross = sw.get_gross_exposure()[0]
        assert gross == pytest.approx(2.0)

    def test_warns_on_non_neutral_portfolio(self):
        """Test that warning is raised for non-neutral portfolios."""
        import warnings

        class MockPortfolioWeights:
            def __init__(self):
                self.long_assets = ["BTC", "ETH"]
                self.short_assets = ["SOL"]

            def to_wide(self):
                return pl.DataFrame({
                    "timestamp": [datetime(2024, 1, 1)],
                    "BTC": [0.4],
                    "ETH": [0.3],
                    "SOL": [-0.2],  # Net = 0.5 (not neutral)
                })

        pw = MockPortfolioWeights()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            StrategyWeights.from_portfolio_weights(pw)

            # Should have raised a warning
            assert len(w) == 1
            assert "not market-neutral" in str(w[0].message)

    def test_no_warning_for_neutral_portfolio(self):
        """Test no warning for market-neutral portfolios."""
        import warnings

        class MockPortfolioWeights:
            def __init__(self):
                self.long_assets = ["BTC"]
                self.short_assets = ["ETH"]

            def to_wide(self):
                return pl.DataFrame({
                    "timestamp": [datetime(2024, 1, 1)],
                    "BTC": [0.5],
                    "ETH": [-0.5],  # Net = 0 (neutral)
                })

        pw = MockPortfolioWeights()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            StrategyWeights.from_portfolio_weights(pw)

            # Should not have raised a warning
            assert len(w) == 0

    def test_handles_zero_weights(self):
        """Test that zero weights are handled correctly."""
        class MockPortfolioWeights:
            def __init__(self):
                self.long_assets = []
                self.short_assets = []

            def to_wide(self):
                return pl.DataFrame({
                    "timestamp": [datetime(2024, 1, 1)],
                    "BTC": [0.0],
                    "ETH": [0.0],
                })

        pw = MockPortfolioWeights()
        sw = StrategyWeights.from_portfolio_weights(pw)

        # Weights should remain 0
        assert sw.weights["BTC"][0] == 0.0
        assert sw.weights["ETH"][0] == 0.0
        # CASH should be 1.0
        assert sw.weights["CASH"][0] == 1.0


@pytest.mark.parametrize(
    ("btc", "eth", "cash", "limit", "message"),
    [
        (float("nan"), 0.0, 1.0, None, "weights.BTC must be finite"),
        (0.2, float("inf"), 0.8, None, "weights.ETH must be finite"),
        (None, 0.2, 0.8, None, "CASH must be null exactly"),
        (0.2, 0.2, None, None, "CASH must be null exactly"),
        (0.2, 0.2, 0.7, None, "Found 1 invalid rows"),
        (0.2, 0.2, 0.6, float("inf"), "quantity_limits.BTC must be finite"),
    ],
)
def test_one_row_validate_matches_the_multi_row_path(btc, eth, cash, limit, message):
    good = {"BTC": 0.1, "ETH": 0.1, "CASH": 0.8}
    bad = {"BTC": btc, "ETH": eth, "CASH": cash}
    def build(rows, limits):
        n = len(rows)
        stamps = [datetime(2024, 1, day + 1) for day in range(n)]
        frame = pl.DataFrame({"timestamp": stamps, **{c: [r[c] for r in rows] for c in ("BTC", "ETH", "CASH")}},
                             schema_overrides={c: pl.Float64 for c in ("BTC", "ETH", "CASH")})
        bounds = pl.DataFrame({"timestamp": stamps, "BTC": limits, "ETH": [None] * n},
                              schema_overrides={"BTC": pl.Float64, "ETH": pl.Float64})
        return StrategyWeights(weights=frame, assets=["BTC", "ETH"], quantity_limits=bounds)
    for weights in (build([bad], [limit]), build([good, bad], [None, limit])):
        with pytest.raises(ValueError, match=message):
            weights.validate()


def _watermarked(days: list[int], observed: list[int | None]) -> StrategyWeights:
    return StrategyWeights(
        weights=pl.DataFrame({"timestamp": [datetime(2024, 1, d) for d in days], "BTC": [1.0] * len(days),
                              "CASH": [0.0] * len(days)}),
        assets=["BTC"],
        observed_through=pl.Series([None if d is None else datetime(2023, 12, d) for d in observed],
                                   dtype=pl.Datetime("us")),
    )


def test_observed_through_round_trips_slices_and_concats(tmp_path):
    weights = _watermarked([1, 2], [30, 31])
    weights.save(tmp_path / "w.parquet")
    loaded = StrategyWeights.from_parquet(tmp_path / "w.parquet")
    assert loaded.observed_through.to_list() == weights.observed_through.to_list()
    assert loaded.weights.columns == ["timestamp", "BTC", "CASH"]
    assert weights.slice(1).observed_through.to_list() == [datetime(2023, 12, 31)]
    plain = StrategyWeights(weights=weights.weights.slice(0, 1).with_columns(
        pl.lit(datetime(2024, 1, 3)).cast(pl.Datetime("us")).alias("timestamp")), assets=["BTC"])
    assert StrategyWeights.concat([weights, plain]).observed_through.to_list() == [
        datetime(2023, 12, 30), datetime(2023, 12, 31), None]


def test_observed_through_must_precede_and_align_with_each_decision():
    with pytest.raises(ValueError, match="precede"):
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "BTC": [1.0], "CASH": [0.0]}),
            assets=["BTC"],
            observed_through=pl.Series([datetime(2024, 1, 1)], dtype=pl.Datetime("us")),
        ).validate()
    with pytest.raises(ValueError, match="aligned"):
        _watermarked([1, 2], [30])
    with pytest.raises(ValueError, match="dtype"):
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "BTC": [1.0], "CASH": [0.0]}),
            assets=["BTC"],
            observed_through=pl.Series([datetime(2023, 12, 1)], dtype=pl.Datetime("us", "UTC")),
        )
