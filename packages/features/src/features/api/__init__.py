"""Public API wrappers for feature publication."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

import polars as pl
from config import QUANT_DB_ROOT
from data.platform.storage import delta_read

from features.blocks import FeatureBlocks
from features.extensions import FeatureFamily, bootstrap_feature_extensions
from features.publication.validation import ASSET_COL, TIMESTAMP_COL

from .presets import list_feature_presets


class FeaturesApiError(RuntimeError):
    """Raised when a feature publication operation fails."""


@dataclass
class FeatureValidationReport:
    """Validation result for the explicit publishable family map."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class FeatureSmokeReport:
    """Smoke result for publishable families."""

    passed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    info: list[str] = field(default_factory=list)


PUBLISHABLE_FAMILIES: dict[str, FeatureFamily] = {}
bootstrap_feature_extensions(PUBLISHABLE_FAMILIES)


def _family(category: str) -> FeatureFamily:
    try:
        return PUBLISHABLE_FAMILIES[category]
    except KeyError as exc:
        known = ", ".join(sorted(PUBLISHABLE_FAMILIES))
        raise FeaturesApiError(f"Unknown publishable feature category '{category}'. Known: {known}") from exc


def _runner_class(family: FeatureFamily):
    module = import_module(family.runner_module)
    return getattr(module, family.runner_class)


def list_feature_catalog() -> list[dict[str, Any]]:
    """Return explicit publishable feature families for CLI display."""
    return [
        {
            "category": family.category,
            "description": family.description,
            "resolutions": list(family.resolutions),
            "asset_column": family.asset_column,
            "runner_module": family.runner_module,
            "runner_class": family.runner_class,
        }
        for family in PUBLISHABLE_FAMILIES.values()
    ]


def family_excluded_assets(category: str) -> dict[str, Any]:
    """A family's reviewed asset exclusions, when its runner declares ``excluded_assets()``; else empty."""
    family = _family(category)
    runner = _runner_class(family).from_preset(overrides={"save": False})
    declared = getattr(runner, "excluded_assets", None)
    if declared is None:
        return {"reviewed_at": None, "method": None, "assets": []}
    return declared()


def family_feature_blocks(category: str) -> FeatureBlocks | None:
    """A family's declared feature blocks, when it registers ``feature_blocks``; else ``None``."""
    return _family(category).feature_blocks


def validate_catalog() -> FeatureValidationReport:
    """Validate the explicit publishable feature family map."""
    report = FeatureValidationReport()
    for family in PUBLISHABLE_FAMILIES.values():
        try:
            runner_cls = _runner_class(family)
        except Exception as exc:  # pragma: no cover - failure path is message-only.
            report.errors.append(f"{family.category}: cannot import runner: {exc}")
            continue
        if not hasattr(runner_cls, "from_preset"):
            report.errors.append(f"{family.category}: runner missing from_preset()")
            continue
        try:
            runner = runner_cls.from_preset(overrides={"save": False})
        except Exception as exc:  # pragma: no cover - depends on family config internals.
            report.errors.append(f"{family.category}: cannot instantiate full panel: {exc}")
            continue
        logical_category = getattr(runner.run_config, "logical_category", runner.run_config.category)
        if logical_category != family.category:
            report.errors.append(f"{family.category}: runner logical category {logical_category!r} does not match")
        if not (
            runner.run_config.category == family.category
            or runner.run_config.category.startswith(f"{family.category}/")
        ):
            report.errors.append(f"{family.category}: runner publish category {runner.run_config.category!r} does not match")
        if runner.run_config.resolution not in family.resolutions:
            report.errors.append(
                f"{family.category}: runner resolution {runner.run_config.resolution!r} "
                f"not in {list(family.resolutions)!r}"
            )
        if bool(runner.run_config.require_asset_column) != family.asset_column:
            report.errors.append(f"{family.category}: runner asset-column contract mismatch")
        report.warnings.extend(_block_warnings(family))
        report.info.append(f"{family.category}: {family.runner_module}.{family.runner_class}")
    return report


# Row keys every panel carries; they are not features and belong to no block.
KEY_COLUMNS = frozenset({TIMESTAMP_COL, ASSET_COL})


def _block_warnings(family: FeatureFamily) -> list[str]:
    """A family without declared blocks, or published full-panel columns no block rule matches."""
    if family.feature_blocks is None:
        return [f"{family.category}: declares no feature blocks"]
    warnings = []
    for resolution in family.resolutions:
        panel = QUANT_DB_ROOT / "features" / resolution / family.category / "data.parquet"
        if delta_read.is_delta_dir(panel.parent):  # a Delta feature table is the category directory
            panel = panel.parent
        elif not panel.exists():
            continue
        columns = [column for column in delta_read.lake_schema(panel) if column not in KEY_COLUMNS]
        unmatched = family.feature_blocks.unmatched(columns)
        if unmatched:
            warnings.append(
                f"{family.category} {resolution}: {len(unmatched)} published column(s) match no feature block: "
                f"{', '.join(unmatched[:10])}"
            )
    return warnings


def smoke_catalog(
    *,
    category: str | None = None,
    execute: bool = False,
) -> FeatureSmokeReport:
    """Instantiate full panels, optionally executing ``run(save=False)``."""
    report = FeatureSmokeReport()
    families = [_family(category)] if category else list(PUBLISHABLE_FAMILIES.values())
    for family in families:
        try:
            runner = _runner_class(family).from_preset(overrides={"save": False})
            if execute:
                runner.run()
        except Exception as exc:
            report.failed[family.category] = str(exc)
            continue
        report.passed.append(family.category)
        report.info.append(f"{family.category}: ok")
    return report


def publish_feature_category(
    *,
    category: str,
    preset: str | None = None,
    resolution: str | None = None,
    force: bool = False,
):
    """Run one publishable feature family and persist it to ``db/features``."""
    family = _family(category)
    if resolution is not None and resolution not in family.resolutions:
        raise FeaturesApiError(
            f"Resolution '{resolution}' is not declared for {category}. Allowed: {list(family.resolutions)}"
        )
    overrides: dict[str, object] = {"save": True, "force": force}
    if resolution is not None:
        overrides["resolution"] = resolution
    runner = _runner_class(family).from_preset(preset, overrides=overrides)
    runner.run_config.save = True
    runner.run_config.force = force
    runner.run_config.created_by = "qf_features_publish"
    if resolution is not None:
        runner.run_config.resolution = resolution
    return runner.run()


__all__ = [
    "FeatureBlocks",
    "FeatureFamily",
    "FeatureSmokeReport",
    "FeatureValidationReport",
    "FeaturesApiError",
    "PUBLISHABLE_FAMILIES",
    "family_excluded_assets",
    "family_feature_blocks",
    "list_feature_catalog",
    "list_feature_presets",
    "publish_feature_category",
    "smoke_catalog",
    "validate_catalog",
]
