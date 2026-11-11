"""Supervised read-only stream over the official Hyperliquid SDK.

Purpose: turn SDK callbacks into bounded immutable FIFO messages with explicit
connection generations and deterministic failure signaling.
USAGE:
    stream = HyperliquidStream(config, subscriptions)
    stream.start()
    envelope = stream.get(timeout_s=5)
    stream.close()
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL

from hyperliquid_client.client import HyperliquidClientConfig
from hyperliquid_client.contracts import StreamEnvelope, StreamSubscription
from hyperliquid_client.exceptions import HyperliquidStreamError, HyperliquidStreamTimeoutError

# --------------------------------------------------------------------------- #
# Stream
# --------------------------------------------------------------------------- #

_NETWORK_URLS = {"mainnet": MAINNET_API_URL, "testnet": TESTNET_API_URL}
_ERROR = object()


class HyperliquidStream:
    """One bounded, reconnecting, read-only provider stream."""

    def __init__(
        self,
        config: HyperliquidClientConfig,
        subscriptions: Sequence[StreamSubscription],
        *,
        queue_size: int = 4096,
        stale_after_s: float = 15.0,
        reconnect_backoff_s: float = 1.0,
        _session_factory: Callable[[], Any] | None = None,
        _wall_ms: Callable[[], int] | None = None,
        _monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        if not subscriptions:
            raise ValueError("at least one stream subscription is required")
        if queue_size <= 0 or stale_after_s <= 0 or reconnect_backoff_s < 0:
            raise ValueError("stream bounds must be positive")
        self.config = config
        self.subscriptions = tuple(subscriptions)
        for subscription in self.subscriptions:
            subscription.to_sdk(config.perp_dexs)
        self._messages: queue.Queue[object] = queue.Queue(maxsize=queue_size)
        self._stale_after_ns = int(stale_after_s * 1_000_000_000)
        self._reconnect_backoff_s = reconnect_backoff_s
        self._wall_ms = _wall_ms or (lambda: time.time_ns() // 1_000_000)
        self._monotonic_ns = _monotonic_ns or time.monotonic_ns
        self._session_factory = _session_factory or self._new_session
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._generation = 0
        self._sequence = 0
        self._l2_seen_ns: dict[StreamSubscription, int] = {}
        self._error: HyperliquidStreamError | None = None

    def _new_session(self) -> Info:
        return Info(
            _NETWORK_URLS[self.config.network],
            skip_ws=False,
            perp_dexs=list(self.config.perp_dexs) or None,
        )

    def start(self) -> None:
        """Start the owned supervisor exactly once."""
        if self._thread is not None:
            raise HyperliquidStreamError("stream has already been started")
        self._thread = threading.Thread(
            target=self._supervise,
            name="hyperliquid-stream",
            daemon=True,
        )
        self._thread.start()

    def get(self, timeout_s: float) -> StreamEnvelope:
        """Return one envelope or raise the terminal stream failure."""
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        try:
            item = self._messages.get(timeout=timeout_s)
        except queue.Empty as exc:
            if self._error is not None:
                raise self._error
            raise HyperliquidStreamTimeoutError("stream receive timed out") from exc
        if item is _ERROR:
            assert self._error is not None
            raise self._error
        assert isinstance(item, StreamEnvelope)
        return item

    def close(self) -> None:
        """Stop and join the owned supervisor."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                raise HyperliquidStreamError("stream supervisor did not stop")

    def _supervise(self) -> None:
        while not self._stop.is_set():
            session: Any | None = None
            try:
                session = self._session_factory()
                with self._lock:
                    self._generation += 1
                    generation = self._generation
                    session_started_ns = self._monotonic_ns()
                    self._l2_seen_ns = {
                        subscription: session_started_ns
                        for subscription in self.subscriptions
                        if subscription.kind == "l2Book"
                    }
                for subscription in self.subscriptions:
                    session.subscribe(
                        subscription.to_sdk(self.config.perp_dexs),
                        self._callback(generation, subscription),
                    )
                while not self._stop.wait(0.1):
                    with self._lock:
                        now_ns = self._monotonic_ns()
                        stale = any(
                            now_ns - last_seen_ns > self._stale_after_ns for last_seen_ns in self._l2_seen_ns.values()
                        )
                    if stale:
                        break
            except Exception as exc:
                if self._stop.is_set():
                    break
                self._set_error(f"stream session failed: {type(exc).__name__}")
                return
            finally:
                if session is not None:
                    try:
                        session.disconnect_websocket()
                    except Exception:
                        if not self._stop.is_set():
                            self._set_error("stream websocket disconnect failed")
                            return
            if not self._stop.wait(self._reconnect_backoff_s):
                continue

    def _callback(
        self,
        generation: int,
        subscription: StreamSubscription,
    ) -> Callable[[Any], None]:
        def receive(payload: Any) -> None:
            try:
                if not isinstance(payload, dict):
                    raise TypeError("stream payload must be a mapping")
                now_ns = self._monotonic_ns()
                with self._lock:
                    if generation != self._generation or self._stop.is_set():
                        return
                    self._sequence += 1
                    sequence = self._sequence
                    if subscription.kind == "l2Book":
                        self._l2_seen_ns[subscription] = now_ns
                envelope = StreamEnvelope(
                    generation=generation,
                    sequence=sequence,
                    subscription=subscription,
                    received_at_utc_ms=self._wall_ms(),
                    received_at_monotonic_ns=now_ns,
                    payload=payload,
                )
                self._messages.put_nowait(envelope)
            except Exception as exc:
                self._set_error(f"stream callback failed: {type(exc).__name__}")

        return receive

    def _set_error(self, message: str) -> None:
        with self._lock:
            if self._error is not None:
                return
            self._error = HyperliquidStreamError(message)
            self._stop.set()
        try:
            self._messages.put_nowait(_ERROR)
        except queue.Full:
            pass


__all__ = ["HyperliquidStream"]
