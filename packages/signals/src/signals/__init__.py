"""Signal framework package for quant-factory."""

from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
_signals_root = Path(__file__).resolve().parents[2]


def _append_namespace_path(path: Path) -> None:
    path_str = str(path)
    if path.exists() and path_str not in __path__:
        __path__.append(path_str)


_families_root = _signals_root / "extensions" / "lib"
if _families_root.exists():
    for _pkg_root in sorted(_families_root.glob("*/src")):
        if _pkg_root.parent.name.startswith("_"):
            continue
        _append_namespace_path(_pkg_root)

from .api import (  # noqa: E402
    SignalsApiError,
    list_catalog,
    publish_catalog,
    smoke_catalog,
    validate_catalog,
)
from .bootstrap import (  # noqa: E402
    import_active_runner_modules,
    import_runner_module,
    populate_signal_registry,
    resolve_signal_runner,
)
from .contracts import (  # noqa: E402
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    validate_prediction_columns,
    validate_prediction_frame,
    validate_predictions_frame,
    validate_signal_frame,
)
from .ids import generate_run_id, validate_identifier  # noqa: E402
from .manifest import (  # noqa: E402
    get_all_presets,
    get_default_preset,
    get_presets_for_signal,
    get_signal_info,
    list_signal_catalog,
    list_signals,
    load_manifest,
)
from .metadata import SignalMetadata, SignalOutput  # noqa: E402
from .naming import (  # noqa: E402
    is_valid_preset_name,
    is_valid_signal_type_name,
    naming_guidance,
    validate_preset_name,
    validate_signal_type_name,
)
from .prediction_store import PredictionStore  # noqa: E402
from .publish import SignalPublishReport  # noqa: E402
from .registry import SignalRegistry  # noqa: E402
from .runner import SignalRunConfig, SignalRunner, SignalRunResult  # noqa: E402
from .validators import (  # noqa: E402
    SignalCatalogValidation,
    SignalSmokeReport,
    smoke_signal_catalog,
    smoke_signals,
    validate_signal_catalog,
)

__all__ = [
    "SignalsApiError",
    "SignalRunner",
    "SignalRunConfig",
    "SignalRunResult",
    "SignalRegistry",
    "SignalMetadata",
    "SignalOutput",
    "PredictionStore",
    "SignalCatalogValidation",
    "SignalPublishReport",
    "SignalSmokeReport",
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "generate_run_id",
    "get_all_presets",
    "get_default_preset",
    "get_presets_for_signal",
    "get_signal_info",
    "is_valid_preset_name",
    "is_valid_signal_type_name",
    "import_active_runner_modules",
    "import_runner_module",
    "list_signal_catalog",
    "list_catalog",
    "list_signals",
    "load_manifest",
    "naming_guidance",
    "populate_signal_registry",
    "publish_catalog",
    "resolve_signal_runner",
    "smoke_catalog",
    "smoke_signal_catalog",
    "smoke_signals",
    "validate_catalog",
    "validate_identifier",
    "validate_preset_name",
    "validate_prediction_columns",
    "validate_prediction_frame",
    "validate_predictions_frame",
    "validate_signal_catalog",
    "validate_signal_frame",
    "validate_signal_type_name",
]
