"""Operator risk rulesets: the configurable pre-trade limits a live run loads.

Purpose: keep risk *policy* (margin mode, leverage, weight and notional caps,
slippage, snapshot freshness, foreign-position blocking) out of venue code.
A ruleset is a TOML file in which every field is required, so a missing limit
refuses the run instead of falling back to a default. Venue facts (exchange
minimums, size precision, maximum leverage) and engine guarantees (identity
proof, at-most-once submit, prove-flat) are not configurable here.

One run loads one ruleset.

USAGE:
    from execution.rulesets import load_ruleset

    rules = load_ruleset(Path("example.toml"))
    print(rules.ruleset_id)  # "example@<fingerprint>"

TOML shape (every key required; write decimals as strings or integers):
    [ruleset]
    name = "example"
    venue = "example-venue"

    [limits]
    margin_mode = "isolated"          # "isolated" or "cross"
    leverage = "2"                    # exact leverage the account must run at
    max_abs_target_weight = "1.0"     # |position notional| / equity; <= leverage
    max_order_notional = "100"        # quote currency
    max_position_notional = "250"     # quote currency
    max_slippage_bps = "25"
    max_snapshot_age_seconds = 5

    [guards]
    block_foreign_positions = true
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from execution._checks import require_finite_decimal, require_non_empty_str

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #

MARGIN_MODES = frozenset({"isolated", "cross"})

_SECTIONS: dict[str, frozenset[str]] = {
    "ruleset": frozenset({"name", "venue"}),
    "limits": frozenset(
        {
            "margin_mode",
            "leverage",
            "max_abs_target_weight",
            "max_order_notional",
            "max_position_notional",
            "max_slippage_bps",
            "max_snapshot_age_seconds",
        }
    ),
    "guards": frozenset({"block_foreign_positions"}),
}


@dataclass(frozen=True, slots=True)
class RiskRuleset:
    """One validated set of operator risk limits for one venue."""

    name: str
    venue: str
    margin_mode: str
    leverage: Decimal
    max_abs_target_weight: Decimal
    max_order_notional: Decimal
    max_position_notional: Decimal
    max_slippage_bps: Decimal
    max_snapshot_age: timedelta
    block_foreign_positions: bool
    fingerprint: str

    def __post_init__(self) -> None:
        require_non_empty_str(self.name, "name")
        require_non_empty_str(self.venue, "venue")
        require_non_empty_str(self.fingerprint, "fingerprint")
        if self.margin_mode not in MARGIN_MODES:
            raise ValueError(f"margin_mode must be one of {sorted(MARGIN_MODES)}")
        for name in (
            "leverage",
            "max_abs_target_weight",
            "max_order_notional",
            "max_position_notional",
            "max_slippage_bps",
        ):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name, positive=True))
        if self.max_abs_target_weight > self.leverage:
            raise ValueError("max_abs_target_weight cannot exceed leverage (margin would exceed equity)")
        if self.max_slippage_bps >= Decimal("10000"):
            raise ValueError("max_slippage_bps must be less than 10000")
        if not isinstance(self.max_snapshot_age, timedelta) or self.max_snapshot_age <= timedelta(0):
            raise ValueError("max_snapshot_age must be a positive timedelta")
        if not isinstance(self.block_foreign_positions, bool):
            raise TypeError("block_foreign_positions must be bool")

    @property
    def ruleset_id(self) -> str:
        """Return the log-safe audit identity recorded with every result."""
        return f"{self.name}@{self.fingerprint}"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"{name} must be a string or integer (no floats)")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} is not a decimal: {value!r}") from None


def parse_ruleset(text: str) -> RiskRuleset:
    """Parse and validate one ruleset; unknown or missing keys refuse."""
    data = tomllib.loads(text)
    if set(data) != set(_SECTIONS):
        raise ValueError(f"ruleset sections must be exactly {sorted(_SECTIONS)}")
    for section, keys in _SECTIONS.items():
        table = data[section]
        if not isinstance(table, dict) or set(table) != keys:
            missing = sorted(keys - set(table)) if isinstance(table, dict) else sorted(keys)
            extra = sorted(set(table) - keys) if isinstance(table, dict) else []
            raise ValueError(f"[{section}] keys mismatch: missing={missing} unknown={extra}")
    head, limits, guards = data["ruleset"], data["limits"], data["guards"]
    age = limits["max_snapshot_age_seconds"]
    if isinstance(age, bool) or not isinstance(age, int):
        raise TypeError("max_snapshot_age_seconds must be an integer")
    return RiskRuleset(
        name=head["name"],
        venue=head["venue"],
        margin_mode=limits["margin_mode"],
        leverage=_decimal(limits["leverage"], "leverage"),
        max_abs_target_weight=_decimal(limits["max_abs_target_weight"], "max_abs_target_weight"),
        max_order_notional=_decimal(limits["max_order_notional"], "max_order_notional"),
        max_position_notional=_decimal(limits["max_position_notional"], "max_position_notional"),
        max_slippage_bps=_decimal(limits["max_slippage_bps"], "max_slippage_bps"),
        max_snapshot_age=timedelta(seconds=age),
        block_foreign_positions=guards["block_foreign_positions"],
        fingerprint=hashlib.sha256(text.encode()).hexdigest()[:12],
    )


def load_ruleset(path: Path) -> RiskRuleset:
    """Load one ruleset file."""
    return parse_ruleset(Path(path).read_text(encoding="utf-8"))


__all__ = ["MARGIN_MODES", "RiskRuleset", "load_ruleset", "parse_ruleset"]
