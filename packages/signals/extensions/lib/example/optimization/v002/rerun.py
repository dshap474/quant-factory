"""example v002 rerun: the volatility-scaled momentum sign on the newest complete inputs.

Scaffold version: the family is registered ``planned``, so this rebuilds the preset in-process
(``save=False``) and nothing publishes it.

USAGE:
    import runpy
    rerun = runpy.run_path("packages/signals/extensions/lib/example/optimization/v002/rerun.py")
    result = rerun["build"]("default").run()
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from signals.example_signal.runner import ExampleRunner

# --------------------------------------------------------------------------- #
# Rerun
# --------------------------------------------------------------------------- #

PRESETS: tuple[str, ...] = ("default",)


def build(preset: str) -> ExampleRunner:
    return ExampleRunner.from_preset(preset, memory_version="v002")
