"""Feature blocks: how a family groups its published columns into named themes.

A family declares its blocks once, as data, and passes them at registration; the catalog
carries them to consumers such as the DB API without importing family code. Rules are
checked in order and the first match wins; patterns are case-sensitive fnmatch globs on
the column name. A column no rule matches has no block, and ``qf-features validate``
lists such columns for every published panel.

USAGE:
    BLOCKS = FeatureBlocks(
        labels={"price": "Price", "flow": "Flow"},          # display order
        rules=(("flow", ("*volume*",)), ("price", ("ret_*", "close"))),
    )
    @FeatureRegistry.register("my/category", feature_blocks=BLOCKS)
    BLOCKS.block("ret_5d")            # "price"
    BLOCKS.unmatched(columns)         # columns no rule declares
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase

# --------------------------------------------------------------------------- #
# Declaration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, eq=False)
class FeatureBlocks:
    """Block labels in display order and the ordered rules that place each column."""

    labels: Mapping[str, str]
    rules: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        unknown = sorted({block for block, _ in self.rules} - set(self.labels))
        if unknown:
            raise ValueError(f"Feature block rules name blocks without a label: {unknown}")

    def block(self, column: str) -> str | None:
        """The block of ``column``, or ``None`` when no rule declares it."""
        for block, patterns in self.rules:
            if any(fnmatchcase(column, pattern) for pattern in patterns):
                return block
        return None

    def unmatched(self, columns: Iterable[str]) -> list[str]:
        """Columns no rule declares, in their given order."""
        return [column for column in columns if self.block(column) is None]


__all__ = ["FeatureBlocks"]
