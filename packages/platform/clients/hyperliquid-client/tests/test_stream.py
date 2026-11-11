"""Hermetic bounded-stream tests.

Purpose: prove exact subscriptions, immutable receive metadata, terminal
callback failure, and idempotent close without provider access.
USAGE: python -m pytest tests/test_stream.py -q
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from hyperliquid_client import (
    HyperliquidClientConfig,
    HyperliquidStream,
    HyperliquidStreamError,
    HyperliquidStreamTimeoutError,
    StreamSubscription,
)

# --------------------------------------------------------------------------- #
# Fake session
# --------------------------------------------------------------------------- #

ACCOUNT = "0x1111111111111111111111111111111111111111"


class Session:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []
        self.subscriptions: list[dict[str, str]] = []
        self.closed = False

    def subscribe(self, subscription: dict[str, str], callback: Any) -> int:
        self.subscriptions.append(subscription)
        self.callbacks.append(callback)
        callback({"data": {"coin": subscription.get("coin"), "time": 1, "levels": [[], []]}})
        return len(self.callbacks)

    def disconnect_websocket(self) -> None:
        self.closed = True


def config() -> HyperliquidClientConfig:
    return HyperliquidClientConfig(
        network="testnet",
        account_address=ACCOUNT,
        perp_dexs=("dexa", "dexb"),
    )


# --------------------------------------------------------------------------- #
# Behavior
# --------------------------------------------------------------------------- #


def test_stream_enqueues_exact_subscription_and_metadata() -> None:
    session = Session()
    stream = HyperliquidStream(
        config(),
        (StreamSubscription("l2Book", coin="dexa:TOKN"),),
        _session_factory=lambda: session,
        _wall_ms=lambda: 10,
        _monotonic_ns=lambda: 20,
        stale_after_s=100,
    )
    stream.start()
    envelope = stream.get(1)
    stream.close()
    assert session.subscriptions == [{"type": "l2Book", "coin": "dexa:TOKN"}]
    assert (envelope.generation, envelope.sequence) == (1, 1)
    assert (envelope.received_at_utc_ms, envelope.received_at_monotonic_ns) == (10, 20)
    assert session.closed


def test_callback_type_failure_is_terminal() -> None:
    session = Session()
    stream = HyperliquidStream(
        config(),
        (StreamSubscription("l2Book", coin="dexa:TOKN"),),
        _session_factory=lambda: session,
        stale_after_s=100,
    )
    stream.start()
    stream.get(1)
    session.callbacks[0]("not-a-mapping")
    with pytest.raises(HyperliquidStreamError, match="callback failed"):
        stream.get(1)
    stream.close()


def test_start_twice_is_rejected() -> None:
    session = Session()
    stream = HyperliquidStream(
        config(),
        (StreamSubscription("l2Book", coin="dexa:TOKN"),),
        _session_factory=lambda: session,
        stale_after_s=100,
    )
    stream.start()
    time.sleep(0.01)
    with pytest.raises(HyperliquidStreamError, match="already"):
        stream.start()
    stream.close()


def test_stale_reconnect_increments_generation_and_ignores_old_callback() -> None:
    sessions: list[Session] = []
    clock = iter(range(0, 1_000_000_000, 2_000_000))

    def session_factory() -> Session:
        session = Session()
        sessions.append(session)
        return session

    stream = HyperliquidStream(
        config(),
        (StreamSubscription("l2Book", coin="dexa:TOKN"),),
        _session_factory=session_factory,
        _monotonic_ns=lambda: next(clock),
        stale_after_s=0.001,
        reconnect_backoff_s=0,
    )
    stream.start()
    first = stream.get(1)
    second = stream.get(1)
    assert (first.generation, second.generation) == (1, 2)
    assert sessions[0].subscriptions == sessions[1].subscriptions

    sessions[0].callbacks[0]({"data": {"coin": "dexa:TOKN"}})
    with pytest.raises(HyperliquidStreamTimeoutError, match="timed out"):
        stream.get(0.01)
    stream.close()


def test_queue_overflow_becomes_terminal() -> None:
    session = Session()
    stream = HyperliquidStream(
        config(),
        (
            StreamSubscription("l2Book", coin="dexa:TOKN"),
            StreamSubscription("l2Book", coin="dexb:TOKN"),
        ),
        queue_size=1,
        _session_factory=lambda: session,
        stale_after_s=100,
    )
    stream.start()
    assert stream.get(1).sequence == 1
    with pytest.raises(HyperliquidStreamError, match="callback failed"):
        stream.get(1)
    stream.close()


# --------------------------------------------------------------------------- #
# Explicit fast-book subscription
# --------------------------------------------------------------------------- #


def test_fast_book_is_explicit_and_preserves_default_payload() -> None:
    assert StreamSubscription("l2Book", coin="dexa:TOKN").to_sdk(("dexa",)) == {
        "type": "l2Book",
        "coin": "dexa:TOKN",
    }
    assert StreamSubscription("l2Book", coin="dexa:TOKN", fast=True).to_sdk(("dexa",)) == {
        "type": "l2Book",
        "coin": "dexa:TOKN",
        "fast": True,
    }
    with pytest.raises(ValueError):
        StreamSubscription("trades", coin="dexa:TOKN", fast=True)
    with pytest.raises(ValueError):
        StreamSubscription("l2Book", coin="dexa:TOKN", fast=1)
