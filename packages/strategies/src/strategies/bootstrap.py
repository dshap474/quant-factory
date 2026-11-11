"""Strategy-family discovery: import every ``extensions/lib/<family>`` runner.

The mechanics live in ``family_registry.FamilyRegistry``; these names keep the
package's public entry points.

USAGE:
    import_active_runner_modules(include_planned=False)   # clear + repopulate StrategyRegistry
    import_runner_module("my-family", reload_module=True)
"""

from __future__ import annotations

from .registry import StrategyRegistry

# --------------------------------------------------------------------------- #
# Discovery entry points
# --------------------------------------------------------------------------- #

iter_strategy_package_dirs = StrategyRegistry.package_dirs
iter_strategy_runner_modules = StrategyRegistry.runner_modules
import_runner_module = StrategyRegistry.import_runner_module
import_active_runner_modules = populate_strategy_registry = StrategyRegistry.populate
