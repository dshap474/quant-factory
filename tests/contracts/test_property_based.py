"""Property-based tests using Hypothesis.

Tests invariants that should hold for any valid input.
"""

from __future__ import annotations

import pytest
import numpy as np

try:
    from hypothesis import given, strategies as st, settings
    import hypothesis.extra.numpy as hnp
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


pytestmark = [
    pytest.mark.statistical,
    pytest.mark.skipif(not HYPOTHESIS_AVAILABLE, reason="hypothesis not installed"),
]


if HYPOTHESIS_AVAILABLE:

    class TestCorrelationInvariants:
        """Property-based tests for correlation metrics."""

        @given(
            x=hnp.arrays(
                np.float64,
                shape=(100,),
                elements=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
            ),
            y=hnp.arrays(
                np.float64,
                shape=(100,),
                elements=st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=50)
        def test_correlation_in_bounds(self, x, y):
            """Correlation is always in [-1, 1]."""
            # Skip if std is zero
            if np.std(x) == 0 or np.std(y) == 0:
                return

            corr = np.corrcoef(x, y)[0, 1]

            if not np.isnan(corr):
                assert -1 <= corr <= 1

        @given(
            x=hnp.arrays(
                np.float64,
                shape=(50,),
                elements=st.floats(min_value=1, max_value=100, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=20)
        def test_self_correlation_is_one(self, x):
            """Correlation of array with itself is 1."""
            if np.std(x) == 0:
                return

            corr = np.corrcoef(x, x)[0, 1]

            assert np.isclose(corr, 1.0, atol=1e-6)


    class TestReturnInvariants:
        """Property-based tests for return calculations."""

        @given(
            prices=hnp.arrays(
                np.float64,
                shape=(100,),
                elements=st.floats(min_value=1, max_value=10000, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=50)
        def test_returns_finite(self, prices):
            """Returns from positive prices are always finite."""
            returns = np.diff(prices) / prices[:-1]

            assert np.isfinite(returns).all()

        @given(
            returns=hnp.arrays(
                np.float64,
                shape=(100,),
                elements=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=50)
        def test_cumulative_returns_positive(self, returns):
            """Cumulative returns from bounded returns are positive."""
            # With returns in [-0.5, 0.5], (1 + r) is always positive
            cumulative = np.prod(1 + returns)

            assert cumulative > 0


    class TestWeightInvariants:
        """Property-based tests for portfolio weights."""

        @given(
            weights=hnp.arrays(
                np.float64,
                shape=(10,),
                elements=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=50)
        def test_normalized_weights_sum_to_one(self, weights):
            """Normalized weights sum to 1."""
            abs_sum = np.abs(weights).sum()
            if abs_sum > 0:
                normalized = weights / abs_sum
                assert np.isclose(np.abs(normalized).sum(), 1.0, atol=1e-6)

        @given(
            n_assets=st.integers(min_value=2, max_value=20),
        )
        @settings(max_examples=20)
        def test_equal_weights_are_normalized(self, n_assets):
            """Equal weights for N assets are normalized."""
            weights = np.ones(n_assets) / n_assets

            assert np.isclose(weights.sum(), 1.0, atol=1e-6)


    class TestOHLCInvariants:
        """Property-based tests for OHLC data."""

        @given(
            open_=st.floats(min_value=1, max_value=1000),
            high=st.floats(min_value=1, max_value=1000),
            low=st.floats(min_value=1, max_value=1000),
            close=st.floats(min_value=1, max_value=1000),
        )
        @settings(max_examples=100)
        def test_valid_ohlc_constraints(self, open_, high, low, close):
            """Valid OHLC has low <= open,close <= high."""
            # Only test if this is a valid OHLC row
            if low <= min(open_, close) and max(open_, close) <= high:
                # Constraint is satisfied
                assert low <= open_ <= high
                assert low <= close <= high

        @given(
            prices=st.lists(
                st.floats(min_value=10, max_value=1000),
                min_size=4,
                max_size=4,
            ),
        )
        @settings(max_examples=50)
        def test_ohlc_from_intraday(self, prices):
            """OHLC from intraday prices is consistent."""
            open_ = prices[0]
            close = prices[-1]
            high = max(prices)
            low = min(prices)

            assert low <= open_ <= high
            assert low <= close <= high


    class TestFeatureInvariants:
        """Property-based tests for features."""

        @given(
            prices=hnp.arrays(
                np.float64,
                shape=(100,),
                elements=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
            ),
            window=st.integers(min_value=2, max_value=20),
        )
        @settings(max_examples=30)
        def test_rolling_mean_in_range(self, prices, window):
            """Rolling mean is between min and max of window."""
            import pandas as pd

            series = pd.Series(prices)
            rolling_mean = series.rolling(window).mean()

            # For each valid point, mean should be in [min, max] of window
            # Note: rolling mean at index i uses values from i-window+1 to i (inclusive)
            for i in range(window - 1, len(prices)):
                window_slice = prices[i - window + 1:i + 1]  # window ending at i
                mean_val = rolling_mean.iloc[i]
                if not np.isnan(mean_val):
                    assert window_slice.min() <= mean_val <= window_slice.max()

        @given(
            values=hnp.arrays(
                np.float64,
                shape=(50,),
                elements=st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False),
            ),
        )
        @settings(max_examples=30)
        def test_zscore_has_zero_mean(self, values):
            """Z-score normalized values have near-zero mean."""
            # Skip if std is effectively zero (constant values)
            std = np.std(values)
            if std == 0 or std < 1e-10:
                return

            zscore = (values - np.mean(values)) / std

            assert np.isclose(np.mean(zscore), 0.0, atol=1e-6)
