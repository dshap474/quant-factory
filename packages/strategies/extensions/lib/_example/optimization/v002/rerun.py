"""v002 rerun: the equal-weight control and the capped 30-session momentum tilt scaled by inverse 20-session volatility, on the newest complete inputs.

USAGE (from the repository root):
    import sys; sys.path.insert(0, "packages/strategies/extensions/lib/_example/src")
    from strategies.backtest_updates import load_rerun
    rerun = load_rerun("_example", "v002")
    result = rerun.build("candidate").run()
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from example_strategy.runner import ExampleRunner

# --------------------------------------------------------------------------- #
# Rerun
# --------------------------------------------------------------------------- #

PRESETS: tuple[str, ...] = ("control", "candidate")


def build(preset: str) -> ExampleRunner:
    return ExampleRunner.from_preset(preset, memory_version="v002")
