"""Run the real DB API against a disposable parquet fixture.

USAGE:
    uv run --package quant-factory-db-api python \
      apps/viz/web/e2e/support/run-db-api-fixture.py --port 18114
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import argparse
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import uvicorn


# --------------------------------------------------------------------------- #
# Fixture
# --------------------------------------------------------------------------- #


def _write_fixture(db_root: Path) -> None:
    """Write one tiny derived dataset discoverable through the real catalog."""
    dataset = db_root / "data" / "derived" / "1d" / "integration" / "release-seam"
    dataset.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [datetime(2026, 8, 30, 12, 0, tzinfo=UTC)],
            "fixture_identity": ["real-fastapi-fixture"],
            "fixture_value": [73.25],
        }
    ).write_parquet(dataset / "data.parquet")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """Serve the disposable fixture until Playwright stops the process."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="qf-viz-db-api-") as temp_dir:
        db_root = Path(temp_dir) / "db"
        _write_fixture(db_root)
        os.environ["DB_API_DB_ROOT"] = str(db_root)

        # Import after setting DB_API_DB_ROOT because Settings is initialized at
        # module import time by the real application entry point.
        from db_api.main import app

        uvicorn.run(
            app,
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
            # Bound Uvicorn's connection drain below Playwright's SIGINT grace
            # period so the TemporaryDirectory context always gets to exit.
            timeout_graceful_shutdown=1,
        )


if __name__ == "__main__":
    main()
