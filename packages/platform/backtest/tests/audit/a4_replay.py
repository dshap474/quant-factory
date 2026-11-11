"""Fresh-process A4 replay entry point.

Purpose: run exactly one public immediate or TWAP world in a newly constructed
Python process and emit its canonical input/result hashes as the final line.

USAGE:
    PYTHONPATH=packages/platform/backtest/tests \
      uv run python -m audit.a4_replay immediate
"""

from __future__ import annotations

import json
import sys

from .a4_support import failure_then_success_fingerprint, replay_fingerprint

# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    modes = {"immediate", "twap", "failure-immediate", "failure-twap"}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        raise SystemExit("usage: python -m audit.a4_replay {immediate|twap|failure-immediate|failure-twap}")
    mode = sys.argv[1]
    kind = mode.removeprefix("failure-")
    operation = failure_then_success_fingerprint if mode.startswith("failure-") else replay_fingerprint
    input_digest, trace_digest = operation(kind)
    print(json.dumps({"input_hash": input_digest, "scenario": mode, "trace_hash": trace_digest}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
