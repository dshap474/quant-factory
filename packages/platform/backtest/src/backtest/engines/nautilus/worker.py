"""One-shot child-process entry point for a prepared Nautilus backtest.

Purpose: contain Nautilus native lifecycle state inside a process that exits
after one engine run so retained dependency graphs cannot accumulate in callers.

USAGE:
    python -m backtest.engines.nautilus.worker  # request is a trusted pickle on stdin
"""

from __future__ import annotations

import pickle
import sys
import traceback

from ...errors import BacktestContractError
from .runtime import run_prepared_execution

# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    """Read one trusted request and write one response to the parent process."""
    try:
        prepared, config = pickle.load(sys.stdin.buffer)  # noqa: S301 - trusted parent process
        result = run_prepared_execution(prepared=prepared, config=config)
        response: tuple[bool, object] = (True, result)
    except Exception as exc:  # noqa: BLE001 - preserve the child boundary diagnostic
        error_kind = "contract" if isinstance(exc, BacktestContractError) else "engine"
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        response = (False, (error_kind, detail))
    pickle.dump(response, sys.stdout.buffer)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
