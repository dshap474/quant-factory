"""Research risk starting-mark regression. USAGE: uv run pytest apps/api/tests/test_research_risk.py -q"""

from datetime import date

import pytest
from db_api.research_risk import surface_risk_metrics

# --------------------------------------------------------------------------- #
# Legacy surfaces may begin with an earned return instead of an anchor
# --------------------------------------------------------------------------- #


def test_first_nonzero_return_is_included() -> None:
    result = surface_risk_metrics([120, 108], [date(2024, 1, 2), date(2024, 1, 3)], first_return=.2)
    assert result["sortino"] == pytest.approx((182.5) ** .5, rel=1e-12)
    assert result["current_drawdown_days"] == 1
