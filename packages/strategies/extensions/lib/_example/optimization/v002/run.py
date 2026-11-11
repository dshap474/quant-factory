"""v002 run: both arms through ``rerun.build``, saved, and judged against the SPEC criterion.

The published backtest and every later paper rerun share one code path: this script only
builds each preset with ``rerun.build`` and runs it. The verdict is the SPEC's: SUPPORTED if
the candidate-minus-control Sharpe delta is at least +0.10, FALSIFIED otherwise.

USAGE:
    uv run python packages/strategies/extensions/lib/_example/optimization/v002/run.py
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import json
import sys
from pathlib import Path

from strategies.backtest_updates import load_rerun

THRESHOLD = 0.10
# The underscore folder keeps the example out of family discovery, so mount its src/ here.
FAMILY_SRC = str(Path(__file__).resolve().parents[2] / "src")
if FAMILY_SRC not in sys.path:
    sys.path.append(FAMILY_SRC)

# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


def evaluate(*, save: bool) -> dict:
    rerun = load_rerun("_example", "v002")
    sharpe, runs = {}, {}
    for preset in rerun.PRESETS:
        runner = rerun.build(preset)
        runner.run_config.save = save
        result = runner.run()
        sharpe[preset], runs[preset] = result.metrics["sharpe"], str(result.run_dir)
    delta = sharpe["candidate"] - sharpe["control"]
    return dict(sharpe=sharpe, delta=delta, verdict="SUPPORTED" if delta >= THRESHOLD else "FALSIFIED", runs=runs)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print(json.dumps(evaluate(save=True), indent=2))
