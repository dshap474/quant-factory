"""Strategy-family registry: extension runners discovered from ``extensions/lib/``.

USAGE:
    StrategyRegistry.get("crypto_example-strategy")       # extension family runner class
"""

from __future__ import annotations

from pathlib import Path

from family_registry import FamilyRegistry

from .paths import STRATEGIES_ROOT, resolve_strategy_path

# --------------------------------------------------------------------------- #
# Strategy runner registry (extension-supplied strategy families)
# --------------------------------------------------------------------------- #


class StrategyRegistry(FamilyRegistry):
    """Registry of strategy-family runners, discovered from ``extensions/lib/``.

    Example:
        @StrategyRegistry.register(
            "example-strategy",
            description="Example directional strategy",
            presets_dir="lib/example-strategy/presets",
        )
        class ExampleStrategyRunner(StrategyRunner):
            ...
    """

    label = "Strategy"
    package_root = STRATEGIES_ROOT
    defaults = {"output_type": "directional"}

    @classmethod
    def resolve_path(cls, path: str) -> Path:
        return resolve_strategy_path(path, STRATEGIES_ROOT)
