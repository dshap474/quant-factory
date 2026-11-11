"""Strategy framework package for quant-factory."""

from __future__ import annotations

import sys

from .paths import FAMILIES_ROOT

__version__ = "0.1.0"

# Families import under one name: their own top-level package (``my_family``), never
# ``strategies.my_family``.
if FAMILIES_ROOT.is_dir():
    for _src in sorted(FAMILIES_ROOT.glob("[!_]*/src")):
        if str(_src) not in sys.path:
            sys.path.append(str(_src))

from .alignment import (  # noqa: E402
    StrategyAlignmentValidation,
    validate_strategy_alignment,
)
from .api import (  # noqa: E402
    StrategyCatalogValidation,
    StrategyRunHandle,
    StrategySmokeReport,
    finalize,
    get_active_preset,
    list_catalog,
    list_families,
    list_presets,
    run,
    scaffold,
    smoke,
    smoke_strategies,
    validate_alignment,
    validate_catalog,
    validate_strategy_catalog,
)
from .bootstrap import (  # noqa: E402
    import_active_runner_modules,
    import_runner_module,
    populate_strategy_registry,
)
from .contracts import validate_strategy_weights_contract  # noqa: E402
from .ids import generate_run_id  # noqa: E402
from .manifest import (  # noqa: E402
    get_all_presets,
    get_default_preset,
    get_presets_for_type,
    get_strategy_info,
    iter_strategy_entries,
    list_strategy_catalog,
    list_strategy_types,
    load_manifest,
)
from .paths import (  # noqa: E402
    EXTENSIONS_ROOT,
    FAMILIES_ROOT,
    STRATEGIES_ROOT,
    resolve_strategy_path,
)
from .registry import StrategyRegistry  # noqa: E402
from .results import BacktestOutput, TrainingMetadata  # noqa: E402
from .runner import AccountState, LedgerInputs, StrategyRunConfig, StrategyRunner, StrategyRunResult  # noqa: E402
from .versioned import (  # noqa: E402
    discover_strategy_versions,
    get_version_dir,
    get_version_final_dir,
    load_version_final_artifact,
    load_version_runs,
    promote_run,
)
from .weights import ExecutionMode, ExecutionTiming, RebalanceMode, StrategyWeights  # noqa: E402

__all__ = [
    "__version__",
    "StrategyRegistry",
    "StrategyRunner",
    "AccountState",
    "LedgerInputs",
    "StrategyRunConfig",
    "StrategyRunResult",
    "StrategyWeights",
    "ExecutionMode",
    "ExecutionTiming",
    "RebalanceMode",
    "BacktestOutput",
    "TrainingMetadata",
    "EXTENSIONS_ROOT",
    "FAMILIES_ROOT",
    "STRATEGIES_ROOT",
    "StrategyCatalogValidation",
    "StrategyAlignmentValidation",
    "StrategySmokeReport",
    "StrategyRunHandle",
    "discover_strategy_versions",
    "finalize",
    "generate_run_id",
    "get_active_preset",
    "get_default_preset",
    "get_all_presets",
    "get_presets_for_type",
    "get_strategy_info",
    "import_active_runner_modules",
    "import_runner_module",
    "iter_strategy_entries",
    "list_catalog",
    "list_families",
    "list_presets",
    "list_strategy_catalog",
    "list_strategy_types",
    "load_manifest",
    "load_version_runs",
    "populate_strategy_registry",
    "resolve_strategy_path",
    "run",
    "scaffold",
    "smoke",
    "smoke_strategies",
    "get_version_dir",
    "get_version_final_dir",
    "load_version_final_artifact",
    "promote_run",
    "validate_catalog",
    "validate_alignment",
    "validate_strategy_alignment",
    "validate_strategy_weights_contract",
    "validate_strategy_catalog",
]
