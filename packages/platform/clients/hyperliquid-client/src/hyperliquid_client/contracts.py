"""Validated value objects for the narrow Hyperliquid client.

Purpose: keep provider request and stream inputs immutable and provider-free.
USAGE:
    request = LimitOrderRequest(
        coin="dexa:TOKN",
        is_buy=True,
        size="1",
        limit_price="0.25",
        time_in_force="Alo",
        reduce_only=False,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_CLOID_RE = re.compile(r"^0x[0-9a-f]{32}$")
_DEFAULT_COIN_RE = re.compile(r"^k?[A-Z][A-Z0-9]*$")
_DEX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
_FIXED_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def validated_address(value: str | None, name: str, *, optional: bool = False) -> str | None:
    """Return one normalized EVM address or reject it."""
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 42-character hexadecimal address")
    return value.lower()


def validated_dex(value: str) -> str:
    """Return one provider DEX name."""
    if not isinstance(value, str) or not _DEX_RE.fullmatch(value) or ":" in value:
        raise ValueError("dex must be a non-empty provider DEX name")
    return value


def validated_coin(value: str, perp_dexs: tuple[str, ...]) -> str:
    """Return one default-DEX or explicitly configured HIP-3 symbol."""
    if not isinstance(value, str):
        raise ValueError("coin must be a provider symbol")
    if ":" not in value:
        if not _DEFAULT_COIN_RE.fullmatch(value):
            raise ValueError("coin must be an uppercase default-DEX symbol")
        return value
    if value.count(":") != 1:
        raise ValueError("HIP-3 coin must contain exactly one colon")
    dex, symbol = value.split(":", 1)
    if dex not in perp_dexs:
        raise ValueError("HIP-3 coin DEX is not explicitly configured")
    if not symbol or symbol.strip() != symbol or any(character.isspace() for character in symbol):
        raise ValueError("HIP-3 coin symbol must be non-empty and contain no whitespace")
    return value


def validated_fixed(value: str, name: str) -> str:
    """Return a positive canonical fixed-point string."""
    if not isinstance(value, str) or not _FIXED_RE.fullmatch(value):
        raise ValueError(f"{name} must be a positive fixed-point string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a positive fixed-point string") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be a positive fixed-point string")
    return value


def validated_cloid(value: str) -> str:
    """Return one strict 128-bit client-order identifier."""
    if not isinstance(value, str) or not _CLOID_RE.fullmatch(value):
        raise ValueError("cloid must be 0x plus 32 lowercase hexadecimal characters")
    return value


def validated_window(start_ms: int, end_ms: int) -> tuple[int, int]:
    """Return one ordered non-negative millisecond interval."""
    if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
        raise ValueError("start_ms must be a non-negative integer")
    if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms <= start_ms:
        raise ValueError("end_ms must be an integer greater than start_ms")
    return start_ms, end_ms


# --------------------------------------------------------------------------- #
# REST and stream contracts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LimitOrderRequest:
    """One allowlisted ALO or IOC limit order."""

    coin: str
    is_buy: bool
    size: str
    limit_price: str
    time_in_force: Literal["Alo", "Ioc"]
    reduce_only: bool
    cloid: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.is_buy, bool) or not isinstance(self.reduce_only, bool):
            raise TypeError("is_buy and reduce_only must be bool")
        validated_fixed(self.size, "size")
        validated_fixed(self.limit_price, "limit_price")
        if self.time_in_force not in ("Alo", "Ioc"):
            raise ValueError("time_in_force must be 'Alo' or 'Ioc'")
        if self.cloid is not None:
            validated_cloid(self.cloid)


_STREAM_KINDS = frozenset(
    {
        "l2Book",
        "bbo",
        "trades",
        "activeAssetCtx",
        "orderUpdates",
        "userFills",
        "userFundings",
    }
)


@dataclass(frozen=True, slots=True)
class StreamSubscription:
    """One allowlisted official-SDK websocket subscription."""

    kind: str
    coin: str | None = None
    user: str | None = None
    dex: str = ""
    fast: bool | None = None

    def __post_init__(self) -> None:
        if self.fast is not None and (self.kind != "l2Book" or not isinstance(self.fast, bool)):
            raise ValueError("fast must be a boolean on l2Book only")
        if self.kind not in _STREAM_KINDS:
            raise ValueError(f"unsupported stream kind: {self.kind}")
        if self.kind in {"l2Book", "bbo", "trades", "activeAssetCtx"} and self.coin is None:
            raise ValueError(f"{self.kind} requires coin")
        if self.kind in {"orderUpdates", "userFills", "userFundings"} and self.user is None:
            raise ValueError(f"{self.kind} requires user")
        if self.user is not None:
            object.__setattr__(self, "user", validated_address(self.user, "user"))
        if self.dex:
            validated_dex(self.dex)

    def to_sdk(self, perp_dexs: tuple[str, ...]) -> dict[str, Any]:
        """Return the exact official-SDK subscription mapping."""
        payload: dict[str, Any] = {"type": self.kind}
        if self.fast is not None:
            payload["fast"] = self.fast
        if self.coin is not None:
            payload["coin"] = validated_coin(self.coin, perp_dexs)
        if self.user is not None:
            payload["user"] = self.user
        if self.dex:
            if self.dex not in perp_dexs:
                raise ValueError("subscription DEX is not explicitly configured")
            payload["dex"] = self.dex
        return payload


@dataclass(frozen=True, slots=True)
class StreamEnvelope:
    """One raw provider message with local ordering and receive metadata."""

    generation: int
    sequence: int
    subscription: StreamSubscription
    received_at_utc_ms: int
    received_at_monotonic_ns: int
    payload: Mapping[str, Any]


__all__ = [
    "LimitOrderRequest",
    "StreamEnvelope",
    "StreamSubscription",
    "validated_address",
    "validated_cloid",
    "validated_coin",
    "validated_dex",
    "validated_fixed",
    "validated_window",
]
