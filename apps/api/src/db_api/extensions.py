"""Discover and register optional DB API extensions.

USAGE::

    load_extensions(app, Path("apps/api/extensions"))
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

from fastapi import FastAPI

# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

ENTRYPOINT_NAME = "extension.py"
_SAFE_MODULE_PART = re.compile(r"[^A-Za-z0-9_]")


class ExtensionError(RuntimeError):
    """An installed extension is malformed or violates the route contract."""


def discover_extensions(extension_root: Path) -> list[Path]:
    """Return direct extension children in deterministic name order."""
    if not extension_root.exists():
        return []
    if not extension_root.is_dir():
        raise ExtensionError(f"Extension root is not a directory: {extension_root}")

    children = sorted(
        (child for child in extension_root.iterdir() if child.is_dir() and not child.name.startswith("_")),
        key=lambda child: child.name,
    )
    for child in children:
        if not (child / ENTRYPOINT_NAME).is_file():
            raise ExtensionError(f"Extension '{child.name}' is missing {ENTRYPOINT_NAME}")
    return children


def _load_module(extension_dir: Path) -> ModuleType:
    entrypoint = extension_dir / ENTRYPOINT_NAME
    module_name = f"db_api_extension_{_SAFE_MODULE_PART.sub('_', extension_dir.name)}"
    spec = importlib.util.spec_from_file_location(module_name, entrypoint)
    if spec is None or spec.loader is None:
        raise ExtensionError(f"Cannot load extension '{extension_dir.name}'")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _route_method_paths(routes: list[object]) -> list[tuple[str, str]]:
    return [
        (method, route.path)
        for route in routes
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
    ]


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def load_extensions(app: FastAPI, extension_root: Path) -> tuple[str, ...]:
    """Load each installed extension and reject duplicate method/path pairs."""
    loaded: list[str] = []
    seen = set(_route_method_paths(app.routes))
    for extension_dir in discover_extensions(extension_root):
        module = _load_module(extension_dir)
        register = getattr(module, "register", None)
        if not callable(register):
            raise ExtensionError(f"Extension '{extension_dir.name}' has no callable register(app)")
        before = len(app.routes)
        register_fn: Callable[[FastAPI], None] = register
        register_fn(app)
        for method_path in _route_method_paths(app.routes[before:]):
            if method_path in seen:
                method, path = method_path
                raise ExtensionError(f"Extension '{extension_dir.name}' duplicates route {method} {path}")
            seen.add(method_path)
        loaded.append(extension_dir.name)
    return tuple(loaded)
