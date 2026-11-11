"""Signal-family discovery: import every ``extensions/lib/<family>`` runner.

The mechanics live in ``family_registry.FamilyRegistry``; these names keep the
package's public entry points.

USAGE:
    import_active_runner_modules(include_planned=False)   # clear + repopulate SignalRegistry
    runner = resolve_signal_runner("example", "default", save=False)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from signals.registry import SIGNALS_ROOT, SignalRegistry

if TYPE_CHECKING:
    from signals.runner import SignalRunner

FAMILIES_ROOT = SIGNALS_ROOT / "extensions" / "lib"

# --------------------------------------------------------------------------- #
# Discovery entry points
# --------------------------------------------------------------------------- #

iter_signal_package_dirs = SignalRegistry.package_dirs
iter_signal_runner_modules = SignalRegistry.runner_modules
qualify_runner_module = SignalRegistry.qualified_module
import_runner_module = SignalRegistry.import_runner_module
import_active_runner_modules = populate_signal_registry = SignalRegistry.populate


# --------------------------------------------------------------------------- #
# Runner resolution
# --------------------------------------------------------------------------- #


def resolve_signal_runner(
    signal_type: str,
    preset: str,
    *,
    save: bool = True,
    db_root: Path | None = None,
) -> "SignalRunner":
    """Return a configured runner for ``signal_type`` and ``preset``.

    One resolution path for every execution surface (smoke, publish): registry
    entry -> runner class -> ``from_preset``.
    """
    runner_cls = SignalRegistry.get(signal_type)
    return runner_cls.from_preset(preset, save=save, db_root=db_root)
