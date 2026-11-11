"""Runtime registry for signal runners.

`output_type` is a coarse runtime hint only. Canonical signal meaning lives in
the family name, family docs, presets, and package-local metadata.

USAGE:
    @SignalRegistry.register(
        "my-signal",
        description="Predict BTC direction",
        presets_dir="extensions/lib/my-signal/presets",
        output_type="classification",
    )
    class MySignalRunner(SignalRunner): ...

    SignalRegistry.get("my-signal")
"""

from __future__ import annotations

from pathlib import Path

from family_registry import FamilyRegistry

SIGNALS_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class SignalRegistry(FamilyRegistry):
    """Registry of signal-family runners mounted as ``signals.<package>.runner``."""

    label = "Signal"
    package_root = SIGNALS_ROOT
    module_prefix = "signals."
    defaults = {"output_type": "time_series", "default_preset": "default"}
