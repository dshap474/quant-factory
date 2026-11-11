"""Canonical primitives for prepared-input semantic fingerprints.

Purpose: serialize shared execution facts deterministically so each prepared
path can hash every input capable of changing fills or reported economics.

USAGE:
    >>> from backtest.preparation.fingerprint import canonical_decimal
    >>> canonical_decimal(Decimal("1.00"))
    '1'
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from execution import FundingSettlement, InstrumentKey, InstrumentSpec
from strategies import StrategyWeights

from ..errors import BacktestContractError
from .targets import decision_times
from .validation import to_decimal

# --------------------------------------------------------------------------- #
# Canonical values
# --------------------------------------------------------------------------- #


def instrument_wire(key: InstrumentKey) -> str:
    """Return the stable venue/symbol wire identity."""
    return f"{key.venue}:{key.symbol}"


def canonical_decimal(value: Decimal) -> str:
    """Return one exponent-independent finite Decimal representation."""
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def canonical_value(value: object) -> str | int | bool:
    """Convert one supported scalar into its stable fingerprint value."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, float):
        return canonical_decimal(Decimal(str(value)))
    if isinstance(value, str):
        return value
    raise BacktestContractError(f"unsupported prepared fingerprint value: {type(value).__name__}")


def strategy_weights_fingerprint(weights: StrategyWeights) -> str:
    """Hash every StrategyWeights fact that can change prepared orders."""
    if not isinstance(weights, StrategyWeights):
        raise BacktestContractError("weights must be StrategyWeights")
    weights.validate()
    decisions = decision_times(weights)
    assets = tuple(sorted(weights.assets))
    rows: list[dict[str, object]] = []
    for row, decision_at in zip(weights.weights.iter_rows(named=True), decisions, strict=True):
        rows.append(
            {
                "timestamp": decision_at.isoformat(timespec="microseconds"),
                "assets": [[asset, canonical_decimal(to_decimal(row[asset], f"weights.{asset}"))] for asset in assets],
                "cash": canonical_decimal(to_decimal(row[weights.cash_col], f"weights.{weights.cash_col}")),
            }
        )
    return sha256_payload(
        {
            "assets": assets,
            "cash_col": weights.cash_col,
            "execution": {
                "mode": weights.execution.mode.value,
                "lag_bars": weights.execution.lag_bars,
                "timestamp_semantics": weights.execution.timestamp_semantics,
            },
            "rows": rows,
        }
    )


# --------------------------------------------------------------------------- #
# Shared execution payloads
# --------------------------------------------------------------------------- #


def instrument_spec_payload(spec: InstrumentSpec) -> dict[str, object]:
    """Return every instrument fact that can change order economics."""
    return {
        "instrument": instrument_wire(spec.key),
        "product": spec.product,
        "base_currency": spec.base_currency,
        "quote_currency": spec.quote_currency,
        "settlement_currency": spec.settlement_currency,
        "is_inverse": spec.is_inverse,
        "multiplier": canonical_decimal(spec.multiplier),
        "price_increment": canonical_decimal(spec.price_increment),
        "quantity_increment": canonical_decimal(spec.quantity_increment),
        "min_quantity": canonical_decimal(spec.min_quantity),
        "max_quantity": canonical_decimal(spec.max_quantity),
        "min_notional": canonical_decimal(spec.min_notional),
        "max_notional": canonical_decimal(spec.max_notional),
        "maker_fee_rate": canonical_decimal(spec.maker_fee_rate),
        "taker_fee_rate": canonical_decimal(spec.taker_fee_rate),
    }


def funding_settlement_payload(settlement: FundingSettlement) -> dict[str, object]:
    """Return one stable funding-settlement payload."""
    return {
        "settlement_id": settlement.settlement_id,
        "instrument": instrument_wire(settlement.instrument),
        "settled_at": canonical_value(settlement.settled_at),
        "rate": canonical_decimal(settlement.rate),
        "mark_price": canonical_decimal(settlement.mark_price),
    }


# --------------------------------------------------------------------------- #
# Digest boundary
# --------------------------------------------------------------------------- #


def sha256_payload(payload: object) -> str:
    """Hash one JSON-compatible canonical payload."""
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_sha256(value: str, name: str) -> None:
    """Validate a lowercase-or-uppercase 64-character SHA-256 hex digest."""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a 64-character SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must contain only hexadecimal characters") from exc


__all__ = [
    "canonical_decimal",
    "canonical_value",
    "funding_settlement_payload",
    "instrument_spec_payload",
    "instrument_wire",
    "sha256_payload",
    "strategy_weights_fingerprint",
    "validate_sha256",
]
