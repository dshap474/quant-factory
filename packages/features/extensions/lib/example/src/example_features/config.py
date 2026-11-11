"""Configure the example feature panel; the field defaults are the full panel.

USAGE: ExampleConfig(save=True)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import QUANT_DB_ROOT

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

@dataclass
class ExampleConfig:
    name: str = "full"
    category: str = "example"
    resolution: str = "1d"
    save: bool = False
    force: bool = False
    description: str = "Example daily close, 1-day return and 30-day momentum (Yahoo BTC and four ETFs)"
    momentum_window: int = 30
    db_root: str | None = None

    def resolved_db_root(self) -> Path:
        return Path(self.db_root) if self.db_root else QUANT_DB_ROOT

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "db_root": str(self.resolved_db_root())}

