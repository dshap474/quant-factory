"""Load the optional Production overlay in deterministic direct-child order.

USAGE: ``load_production_extensions()`` before operations requiring private policy.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from production.contracts import DeploymentValidationError

# --------------------------------------------------------------------------- #
# Extension paths
# --------------------------------------------------------------------------- #

PRODUCTION_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS_ROOT = PRODUCTION_PACKAGE_ROOT / "extensions"


# --------------------------------------------------------------------------- #
# Deterministic loading
# --------------------------------------------------------------------------- #

_loaded_paths: set[Path] = set()
_loaded_modules: set[str] = set()


def _entry_paths(root: Path) -> tuple[Path, ...]:
    adapters_root = root / "adapters"
    deployments_root = root / "deployments"
    adapters = (
        tuple(path for path in sorted(adapters_root.glob("*.py")) if not path.name.startswith("_"))
        if adapters_root.is_dir()
        else ()
    )
    deployments = (
        tuple(
            family_root / "register.py"
            for family_root in sorted(deployments_root.iterdir())
            if family_root.is_dir() and not family_root.name.startswith("_") and (family_root / "register.py").is_file()
        )
        if deployments_root.is_dir()
        else ()
    )
    return adapters + deployments


def _module_name(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return f"_quant_factory_production_extension_{path.stem}_{digest}"


def _load_module(path: Path) -> ModuleType:
    name = _module_name(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DeploymentValidationError(f"could not load Production extension: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    _loaded_modules.add(name)
    return module


def load_production_extensions(root: Path | None = None) -> None:
    """Load and register direct adapter and deployment entries exactly once."""
    extensions_root = (root or EXTENSIONS_ROOT).resolve()
    if not extensions_root.is_dir():
        return
    for path in _entry_paths(extensions_root):
        resolved = path.resolve()
        if resolved in _loaded_paths:
            continue
        module = _load_module(resolved)
        register = getattr(module, "register", None)
        if not callable(register):
            raise DeploymentValidationError(f"Production extension must define register(): {resolved}")
        register()
        _loaded_paths.add(resolved)


def _reset_extension_loader_for_tests() -> None:
    """Forget loaded modules so isolated tests can supply a fresh overlay."""
    _loaded_paths.clear()
    for name in _loaded_modules:
        sys.modules.pop(name, None)
    _loaded_modules.clear()


__all__ = ["EXTENSIONS_ROOT", "PRODUCTION_PACKAGE_ROOT", "load_production_extensions"]
