"""Fresh-process A9 batch, environment, import, and interruption entry point.

Purpose: provide a hermetic child-process contract for concurrency,
environment determinism, repeated imports, and forced process termination.

USAGE:
    PYTHONPATH=packages/platform/backtest/tests \
      uv run python -m audit.a9_replay batch 10 twap
"""

from __future__ import annotations

import importlib
import json
import sys
import time

from .a4_support import replay_fingerprint

# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #


def _batch(count: int, first: str) -> dict[str, object]:
    order = (first, "twap" if first == "immediate" else "immediate")
    observed: dict[str, set[tuple[str, str]]] = {"immediate": set(), "twap": set()}
    for index in range(count):
        for kind in order if index % 2 == 0 else tuple(reversed(order)):
            observed[kind].add(replay_fingerprint(kind))
    return {kind: [list(item) for item in sorted(values)] for kind, values in observed.items()}


def _imports(count: int) -> dict[str, object]:
    import backtest

    import execution

    for _ in range(count):
        importlib.reload(execution)
        importlib.reload(backtest)
    return {
        "backtest_version": backtest.__version__,
        "execution_version": execution.__version__,
        "immediate": replay_fingerprint("immediate"),
    }


def _interrupt(stage: str) -> None:
    print(json.dumps({"ready": stage}), flush=True)
    time.sleep(300)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: a9_replay {batch|imports|interrupt} ...")
    mode = sys.argv[1]
    if mode == "batch" and len(sys.argv) == 4:
        print(json.dumps(_batch(int(sys.argv[2]), sys.argv[3]), sort_keys=True))
        return 0
    if mode == "imports" and len(sys.argv) == 3:
        print(json.dumps(_imports(int(sys.argv[2])), sort_keys=True))
        return 0
    if mode == "interrupt" and len(sys.argv) == 3:
        _interrupt(sys.argv[2])
        return 0
    raise SystemExit("invalid a9_replay arguments")


if __name__ == "__main__":
    raise SystemExit(main())
