"""Unit tests for the FREDClientAdapter.

USAGE:
    uv run pytest packages/platform/clients/fred-client/tests -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fred_client import FREDClientAdapter

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _load_json(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_fred_observations_to_frame():
    adapter = FREDClientAdapter(api_key="demo")
    frame = adapter.observations_to_frame(_load_json("fred_observations.json"))
    assert frame.shape == (2, 4)
    assert frame["value"].to_list() == ["5.25", "5.50"]


def test_fred_series_to_frame():
    adapter = FREDClientAdapter(api_key="demo")
    frame = adapter.series_to_frame(
        {
            "seriess": [
                {
                    "id": "FEDFUNDS",
                    "title": "Federal Funds Effective Rate",
                    "frequency": "Monthly",
                    "units": "Percent",
                }
            ]
        }
    )
    assert frame.shape == (1, 4)
    assert frame["id"].to_list() == ["FEDFUNDS"]


def test_fred_adapter_uses_client_environment_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import fred_client.adapter as fred_module

    seen: dict[str, object] = {}

    class FakeFredClient:
        def __init__(self, **kwargs) -> None:
            seen.update(kwargs)

        def close(self) -> None:
            return None

    monkeypatch.setattr(fred_module, "FredClient", FakeFredClient)

    adapter = fred_module.FREDClientAdapter()
    adapter.close()

    assert seen["api_key"] is None
    assert "environment" not in seen
