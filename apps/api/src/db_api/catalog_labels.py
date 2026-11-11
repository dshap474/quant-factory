"""Optional catalog display labels; machine names and paths remain unchanged.

USAGE: labels = load_catalog_labels(extension_root / "catalog-labels.json")
       catalog_path_labels("raw/1d/vendor-name/prices", labels)
       register_raw_family_rule(app, "vendor-name", depth=3)  # from an extension's register(app)
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import json
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

# --------------------------------------------------------------------------- #
# Metadata and presentation
# --------------------------------------------------------------------------- #


def load_catalog_labels(path: Path) -> dict[str, str]:
    """Load the instance's plain label dictionary; a missing file means none."""
    if not path.exists():
        return {}
    labels = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(labels, dict) or any(
        not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
        for key, value in labels.items()
    ):
        raise ValueError(f"Catalog labels must be a dictionary of nonempty strings: {path}")
    return labels


def human_label(value: str) -> str:
    """Conservative fallback for an unregistered provider or dataset slug."""
    tail = value.strip("/").split("/")[-1] if value.strip("/") else value
    words = tail.replace("_", " ").replace("-", " ").split()
    return " ".join(word.upper() if word.lower() in {"btc"} else word.title() for word in words)


def catalog_path_labels(path: str, labels: dict[str, str]) -> list[str]:
    """Label known names and unknown raw providers without rewriting file names."""
    parts = path.strip("/").split("/") if path.strip("/") else []
    result = [labels.get(part, part) for part in parts]
    if parts and parts[0] == "raw":
        provider = 2 if len(parts) > 1 and re.fullmatch(r"\d+[smhdw]|tick", parts[1]) else 1
        if provider < len(parts):
            result[provider] = labels.get(parts[provider], human_label(parts[provider]))
    return result


# --------------------------------------------------------------------------- #
# Raw family rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RawFamilyRule:
    """Collapse raw paths under ``prefix`` to their first ``depth`` parts.

    When ``second_levels`` is set, the rule applies only when the second path part is one of them.
    """

    prefix: str
    depth: int
    second_levels: frozenset[str] | None = None

    def family(self, parts: list[str]) -> str | None:
        """Return the collapsed family path, or None when this rule does not apply."""
        if len(parts) < self.depth or parts[0] != self.prefix:
            return None
        if self.second_levels is not None and (len(parts) < 2 or parts[1] not in self.second_levels):
            return None
        return "/".join(parts[: self.depth])


def register_raw_family_rule(
    app: FastAPI, prefix: str, depth: int, second_levels: set[str] | frozenset[str] | None = None
) -> None:
    """Register an instance-specific raw family collapsing rule on one application."""
    if not prefix.strip("/") or "/" in prefix.strip("/") or depth < 1:
        raise ValueError(f"Invalid raw family rule: prefix={prefix!r} depth={depth}")
    rule = RawFamilyRule(prefix.strip("/"), depth, None if second_levels is None else frozenset(second_levels))
    app.state.raw_family_rules = (*raw_family_rules(app), rule)


def raw_family_rules(app: FastAPI) -> tuple[RawFamilyRule, ...]:
    """Return the application's registered raw family rules; none by default."""
    return getattr(app.state, "raw_family_rules", ())
