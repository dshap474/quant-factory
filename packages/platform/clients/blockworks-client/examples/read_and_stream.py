"""Fetch a small asset-price sample and export to a caller-selected destination.

USAGE (with BLOCKWORKS_API_KEY in the environment):
    uv run python packages/platform/clients/blockworks-client/examples/read_and_stream.py ASSET_ID OUTPUT.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from blockworks_client import BlockworksClient

# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    with BlockworksClient() as client:
        response = client.timeseries.single("asset-price", "1d", args.asset_id, timeframe="7d")
        print(f"Received {len(response.body['data']['points'])} points")
        count = client.timeseries.export_single(
            "asset-price", "1d", args.asset_id, args.destination, format="csv", timeframe="7d"
        )
        print(f"Wrote {count} bytes to the selected destination")


if __name__ == "__main__":
    main()
