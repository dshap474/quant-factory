"""example v001 rerun: the unscaled 30-day momentum preset, which v002 uses as its control.

v001 itself never ran; this rebuilds its preset on the newest complete inputs.

USAGE (from the repository root):
    import sys; sys.path.insert(0, "packages/signals/extensions/lib/example/src")
    from example_signal.runner import ExampleRunner
    import runpy; m = runpy.run_path("packages/signals/extensions/lib/example/optimization/version/v001/rerun.py")
    runner = m["build"]("default")
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from example_signal.runner import ExampleRunner

# --------------------------------------------------------------------------- #
# Rerun
# --------------------------------------------------------------------------- #

PRESETS: tuple[str, ...] = ("default",)


def build(preset: str) -> ExampleRunner:
    return ExampleRunner.from_preset(preset, memory_version="v001")
