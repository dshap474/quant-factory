"""Analyze supplied tree statistics, held-out permutations, and single-feature fits.

Usage: import operations from ``.mdi``, ``.permutation``, or ``.single_feature``.
Training and preprocessing remain the caller's responsibility.
"""

# --------------------------------------------------------------------------- #
# Public concept modules
# --------------------------------------------------------------------------- #

from fractions import Fraction
from math import fsum, sqrt

import numpy as np
from numpy.typing import NDArray

# --------------------------------------------------------------------------- #
# Shared finite-score reductions
# --------------------------------------------------------------------------- #


def _moments(values: NDArray[np.float64], *, ddof: int) -> tuple[float | None, float | None]:
    """Preserve small spreads and cancellation while avoiding squared overflow."""
    if not len(values):
        return None, None
    try:
        mean = fsum(values) / len(values)
    except OverflowError:
        # Rare extreme scores can overflow their sum while their mean is finite.
        # Exact rational summation also retains residuals after huge cancellation.
        mean = float(sum((Fraction(float(value)) for value in values), Fraction()) / len(values))
    if len(values) <= ddof:
        return mean, None
    with np.errstate(over="ignore"):
        delta = values - values[0]
    if np.isfinite(delta).all():
        scale = float(np.max(np.abs(delta)))
        normalized = delta / scale if scale else delta
    else:
        # A finite pair difference may be unrepresentable; its normalized spread
        # is still representable when the original magnitudes are scaled first.
        scale = float(np.max(np.abs(values)))
        normalized = values / scale
    center = fsum(normalized) / len(values)
    variance = fsum(float(value - center) ** 2 for value in normalized) / (len(values) - ddof)
    std = sqrt(variance) * scale
    if not np.isfinite(mean) or not np.isfinite(std):
        raise ArithmeticError("descriptive moments are outside the finite Float64 range")
    return mean, std
