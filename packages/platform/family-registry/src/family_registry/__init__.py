"""Decorator registry and ``extensions/lib`` discovery for package families.

A consuming package subclasses ``FamilyRegistry`` once; each subclass keeps its own
tables. Families are ``runner.py`` modules under ``<package_root>/extensions/lib/<family>/src/<package>/``
(subpackages included) that register their runner class with the decorator. Runners loaded from
``_archive/`` or ``optimization/version/`` paths are never registered, and a class from
another source file cannot take over a registered name.

USAGE:
    class StrategyRegistry(FamilyRegistry):
        label = "Strategy"
        package_root = STRATEGIES_ROOT
        defaults = {"output_type": "directional"}

    @StrategyRegistry.register("my-family", presets_dir="extensions/lib/my-family/presets")
    class MyRunner: ...

    StrategyRegistry.populate()                    # import every family runner
    StrategyRegistry.catalog()                     # {name: metadata}; discovers on first read
    StrategyRegistry.presets("my-family")          # preset names in the family presets_dir
    StrategyRegistry.import_runner_module("my-family", reload_module=True)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, ClassVar, TypeVar

__all__ = ["FamilyRegistry", "is_historical_module"]

RunnerT = TypeVar("RunnerT", bound=type)

# --------------------------------------------------------------------------- #
# Historical-copy detection
# --------------------------------------------------------------------------- #


def _runner_file(runner_cls: type) -> str | None:
    """Source file of ``runner_cls``, whatever name its module was imported under."""
    module_file = getattr(sys.modules.get(runner_cls.__module__), "__file__", None)
    if module_file is None:
        # Historical experiment loaders may execute a module without inserting it
        # into sys.modules. A method defined on the class still names its file.
        module_file = next(
            (value.__code__.co_filename for value in runner_cls.__dict__.values() if hasattr(value, "__code__")),
            None,
        )
    return None if module_file is None else str(Path(module_file).resolve())


def is_historical_module(runner_cls: type) -> bool:
    """Whether ``runner_cls`` was loaded from an ``_archive/`` or ``optimization/version/`` path."""
    module_file = _runner_file(runner_cls)
    if module_file is None:
        return False
    parts = Path(module_file).parts
    return "_archive" in parts or any(a == "optimization" and b == "version" for a, b in zip(parts, parts[1:]))


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class FamilyRegistry:
    """Class-level runner registry; subclass once per consuming package."""

    label: ClassVar[str] = "Family"
    package_root: ClassVar[Path | None] = None
    module_prefix: ClassVar[str] = ""
    defaults: ClassVar[dict[str, Any]] = {}

    _registry: ClassVar[dict[str, type]] = {}
    _metadata: ClassVar[dict[str, dict[str, Any]]] = {}
    _discovered: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._registry, cls._metadata, cls._discovered = {}, {}, False

    @classmethod
    def register(cls, name: str, **metadata: Any) -> Callable[[RunnerT], RunnerT]:
        """Decorator registering a runner class under ``name`` with catalog metadata."""

        def decorator(runner_cls: RunnerT) -> RunnerT:
            if is_historical_module(runner_cls):
                return runner_cls
            existing = cls._registry.get(name)
            # Identity is the source file, not the import name: one runner.py imported as both
            # ``<pkg>.runner`` and ``signals.<pkg>.runner`` is the same runner, not a takeover.
            if existing is not None and (_runner_file(existing), existing.__qualname__) != (
                _runner_file(runner_cls),
                runner_cls.__qualname__,
            ):
                raise ValueError(
                    f"{cls.label} '{name}' is already registered by {existing.__module__}.{existing.__qualname__}"
                )
            cls._registry[name] = runner_cls
            cls._metadata[name] = {
                "name": name,
                "status": "active",
                "description": "",
                "presets_dir": "",
                **cls.defaults,
                "runner_module": runner_cls.__module__.removeprefix(cls.module_prefix),
                **metadata,
                "runner_class": runner_cls.__name__,
            }
            return runner_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type:
        if name not in cls._registry:
            raise KeyError(f"{cls.label} '{name}' not found. Available: {', '.join(sorted(cls._registry))}")
        return cls._registry[name]

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._registry)

    @classmethod
    def get_metadata(cls, name: str) -> dict[str, Any]:
        if name not in cls._metadata:
            raise KeyError(f"{cls.label} '{name}' not found")
        return dict(cls._metadata[name])

    @classmethod
    def all_metadata(cls) -> dict[str, dict[str, Any]]:
        return {name: dict(meta) for name, meta in cls._metadata.items()}

    @classmethod
    def unregister(cls, name: str) -> None:
        cls._registry.pop(name, None)
        cls._metadata.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        """Drop every registration; the next catalog read rediscovers."""
        cls._registry.clear()
        cls._metadata.clear()
        cls._discovered = False

    # ----------------------------------------------------------------------- #
    # Discovery
    # ----------------------------------------------------------------------- #

    @classmethod
    def package_dirs(cls) -> list[Path]:
        """Family directories: non-underscore ``extensions/lib/<family>/`` with a ``src/``."""
        root = cls.package_root / "extensions" / "lib" if cls.package_root else None
        if root is None or not root.is_dir():
            return []
        return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "src").is_dir())

    @classmethod
    def runner_modules(cls) -> list[str]:
        """``<prefix><package>[.<sub>...].runner`` for every ``runner.py`` under ``<family>/src/<package>/``.

        Subpackages let one family package hold several categories; ``_``-prefixed
        directories (``_archive``) are never discovered.
        """
        return sorted({
            cls.module_prefix + ".".join(runner.relative_to(src).with_suffix("").parts)
            for family_dir in cls.package_dirs()
            for src in [family_dir / "src"]
            for runner in src.glob("*/**/runner.py")
            if not any(part.startswith("_") for part in runner.relative_to(src).parts[:-1])
        })

    @classmethod
    def populate(cls, *, include_planned: bool = False) -> list[str]:
        """Clear, import (or reload) every family runner, and drop ``planned`` ones unless asked."""
        cls.clear()
        for module_name in cls.runner_modules():
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
        for name in cls.list():
            if cls._metadata[name].get("status") == "planned" and not include_planned:
                cls.unregister(name)
        cls._discovered = True
        return cls.list()

    @classmethod
    def import_runner_module(cls, name: str, *, reload_module: bool = False) -> ModuleType:
        """Import the runner module the catalog records for ``name``."""
        runner_module = (cls.info(name) or {}).get("runner_module")
        if not runner_module:
            raise KeyError(f"{cls.label} type not in catalog: {name}")
        module_name = cls.qualified_module(str(runner_module))
        if module_name in sys.modules and (reload_module or name not in cls._registry):
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)

    @classmethod
    def qualified_module(cls, runner_module: str) -> str:
        return runner_module if runner_module.startswith(cls.module_prefix) else cls.module_prefix + runner_module

    # ----------------------------------------------------------------------- #
    # Catalog
    # ----------------------------------------------------------------------- #

    @classmethod
    def catalog(cls) -> dict[str, dict[str, Any]]:
        """``{name: metadata}`` for every registered family, discovering on first read."""
        if not cls._discovered:
            cls.populate(include_planned=True)
        return {
            name: {"docs": f"extensions/lib/{name}/README.md", **{k: v for k, v in meta.items() if k != "name"}}
            for name, meta in sorted(cls._metadata.items())
        }

    @classmethod
    def info(cls, name: str) -> dict[str, Any] | None:
        return cls.catalog().get(name)

    @classmethod
    def resolve_path(cls, path: str) -> Path:
        """Resolve package-relative catalog metadata against ``package_root``."""
        candidate = Path(path)
        if candidate.is_absolute() or cls.package_root is None:
            return candidate
        return cls.package_root / candidate

    @classmethod
    def get_presets_dir(cls, name: str) -> Path | None:
        presets_dir = cls._metadata.get(name, {}).get("presets_dir")
        return cls.resolve_path(presets_dir) if isinstance(presets_dir, str) and presets_dir else None

    @classmethod
    def presets(cls, name: str) -> list[str]:
        """Preset names (``*.yaml`` stems) in the family presets directory."""
        if not cls._discovered:
            cls.populate(include_planned=True)
        path = cls.get_presets_dir(name)
        return sorted(p.stem for p in path.glob("*.yaml")) if path is not None and path.is_dir() else []

    @classmethod
    def default_preset(cls, name: str) -> str | None:
        """The registered ``default_preset`` when it names an existing preset."""
        default = (cls.info(name) or {}).get("default_preset")
        return default if isinstance(default, str) and default in cls.presets(name) else None
