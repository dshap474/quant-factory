"""WebSocket transport wrappers over the official coinbase-advanced-py SDK.

Purpose: own reconnection for market-data and user channels. The SDK is built
with ``retry=False`` because its auto-reconnect drops empty-product-list
subscriptions (heartbeats) on resubscribe, and
``run_forever_with_exception_check`` is an unstoppable loop.

Each stream runs a supervisor thread: connect → subscribe ALL channels → poll
liveness; on any failure close, fire ``on_reset``, backoff (exponential +
jitter, unbounded), reconnect with a **fresh** SDK client, resubscribe
everything. ``stop()`` joins cleanly. Messages are JSON-parsed and forwarded
raw — no business logic.

USAGE:
    from coinbase_advanced_client import MarketDataStream, UserStream

    def on_msg(msg: dict) -> None:
        print(msg.get("channel"), msg.get("sequence_num"))

    md = MarketDataStream(product_ids=["BTC-USDC"], on_message=on_msg)
    md.start()
    ...
    md.stop()

    user = UserStream(product_ids=["BTC-USDC"], on_message=on_msg)
    user.start()
    ...
    user.stop()
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from coinbase.websocket import WSClient, WSUserClient

from .exceptions import CoinbaseAdvancedConfigurationError

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 0.25
_BACKOFF_BASE_S = 0.5
_BACKOFF_MAX_S = 30.0
_JOIN_TIMEOUT_S = 10.0

OnMessage = Callable[[dict[str, Any]], None]
OnReset = Callable[[], None]
ClientFactory = Callable[..., Any]


# --------------------------------------------------------------------------- #
# Credential resolution (identical key names to CoinbaseAdvanced)
# --------------------------------------------------------------------------- #


def _resolve_credentials(
    api_key_name: str | None,
    private_key: str | None,
    *,
    require: bool,
) -> tuple[str | None, str | None]:
    """Resolve environment/argument credentials. Partial credentials always fail closed.

    When ``require`` is True, both must be present. When False (public market
    data), both-absent is allowed; if keys are present they are returned.
    """
    if api_key_name is None and private_key is None:
        api_key_name = os.environ.get("COINBASE_ADVANCED_API_KEY_NAME")
        private_key = os.environ.get("COINBASE_ADVANCED_PRIVATE_KEY")
    if (api_key_name is None) != (private_key is None):
        raise CoinbaseAdvancedConfigurationError(
            "incomplete Coinbase Advanced credentials: pass both api_key_name and private_key"
        )
    if api_key_name is None:
        if not require:
            return None, None
        raise CoinbaseAdvancedConfigurationError(
            "COINBASE_ADVANCED_API_KEY_NAME and COINBASE_ADVANCED_PRIVATE_KEY are required; "
            "set them in the environment."
        )
    if not api_key_name or not private_key:
        raise CoinbaseAdvancedConfigurationError("Coinbase Advanced credentials must not be empty")
    return api_key_name, private_key


def _shutdown_sdk_client(client: Any) -> None:
    """Fully shut down an SDK WS client; tolerate already-closed sockets.

    The SDK's ``close()`` blocks forever (untimed ``future.result()``) if its
    internal event loop is wedged, so run it on a bounded helper thread and
    fall back to force-stopping the loop/thread on timeout or error.
    """
    if client is None:
        return
    close_failed = threading.Event()

    def _close() -> None:
        try:
            client.close()
        except Exception:
            close_failed.set()

    closer = threading.Thread(target=_close, name="cb-ws-close", daemon=True)
    closer.start()
    closer.join(timeout=_JOIN_TIMEOUT_S)
    if not closer.is_alive() and not close_failed.is_set():
        return
    # close() hung or the socket was already dead: force-stop loop/thread.
    loop = getattr(client, "loop", None)
    thread = getattr(client, "thread", None)
    try:
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(loop.stop)
    except Exception:
        pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=_JOIN_TIMEOUT_S)
    try:
        if loop is not None and not loop.is_closed():
            loop.close()
    except Exception:
        pass


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with full jitter; attempt is 0-based after first failure."""
    exp = min(_BACKOFF_MAX_S, _BACKOFF_BASE_S * (2**attempt))
    return random.uniform(0.0, exp)


# --------------------------------------------------------------------------- #
# Shared supervisor
# --------------------------------------------------------------------------- #


class _StreamSupervisor:
    """Supervisor thread that owns connect / subscribe / poll / reconnect."""

    def __init__(
        self,
        *,
        name: str,
        product_ids: Sequence[str],
        on_message: OnMessage,
        on_reset: OnReset | None,
        api_key: str | None,
        api_secret: str | None,
        client_factory: ClientFactory,
        subscribe: Callable[[Any, list[str]], None],
    ) -> None:
        if not product_ids:
            raise ValueError("product_ids must be non-empty")
        if on_message is None:
            raise ValueError("on_message is required")
        self._name = name
        self._product_ids = list(product_ids)
        self._on_message = on_message
        self._on_reset = on_reset
        self._api_key = api_key
        self._api_secret = api_secret
        self._client_factory = client_factory
        self._subscribe = subscribe

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._client_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError(f"{self._name} already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"coinbase-{self._name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._client_lock:
            client = self._client
            self._client = None
        _shutdown_sdk_client(client)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_S)
        self._thread = None

    # -- supervisor loop ---------------------------------------------------- #

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                self._session()
                # Clean session exit (stop requested) — leave loop.
                if self._stop.is_set():
                    break
                # Unexpected clean exit of session without stop: treat as reset.
                failures += 1
                self._fire_reset()
                self._sleep_backoff(failures - 1)
            except Exception:
                logger.exception("%s session failed", self._name)
                failures += 1
                self._fire_reset()
                if self._stop.is_set():
                    break
                self._sleep_backoff(failures - 1)

    def _session(self) -> None:
        # Always build a fresh SDK client per connection attempt.
        with self._client_lock:
            previous = self._client
            self._client = None
        _shutdown_sdk_client(previous)

        if self._stop.is_set():
            return

        client = self._client_factory(
            api_key=self._api_key,
            api_secret=self._api_secret,
            on_message=self._handle_raw_message,
            retry=False,
        )
        with self._client_lock:
            self._client = client

        try:
            client.open()
            self._subscribe(client, self._product_ids)
            while not self._stop.is_set():
                client.raise_background_exception()
                time.sleep(_POLL_INTERVAL_S)
        finally:
            with self._client_lock:
                current = self._client
                if current is client:
                    self._client = None
            _shutdown_sdk_client(client)

    def _handle_raw_message(self, raw: str) -> None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("%s dropped non-JSON message", self._name)
            return
        if not isinstance(parsed, dict):
            logger.warning("%s dropped non-object message", self._name)
            return
        try:
            self._on_message(parsed)
        except Exception:
            logger.exception("%s on_message callback raised", self._name)

    def _fire_reset(self) -> None:
        if self._on_reset is None:
            return
        try:
            self._on_reset()
        except Exception:
            logger.exception("%s on_reset callback raised", self._name)

    def _sleep_backoff(self, attempt: int) -> None:
        delay = _backoff_seconds(attempt)
        # Interruptible sleep so stop() is responsive.
        end = time.monotonic() + delay
        while not self._stop.is_set() and time.monotonic() < end:
            time.sleep(min(0.05, end - time.monotonic()))


# --------------------------------------------------------------------------- #
# Public streams
# --------------------------------------------------------------------------- #


def _subscribe_market(client: Any, product_ids: list[str]) -> None:
    """Subscribe ticker + heartbeats (empty-product channel re-owned on reconnect)."""
    client.ticker(product_ids)
    client.heartbeats()


def _subscribe_user(client: Any, product_ids: list[str]) -> None:
    """Subscribe user + heartbeats."""
    client.user(product_ids)
    client.heartbeats()


class MarketDataStream:
    """Supervisor-owned market-data WS (ticker + heartbeats).

    Market-data channels are public: credentials are optional. If keys are
    present they are passed through; partial credentials fail closed before
    the supervisor starts.
    """

    def __init__(
        self,
        product_ids: Sequence[str],
        on_message: OnMessage,
        *,
        on_reset: OnReset | None = None,
        api_key_name: str | None = None,
        private_key: str | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        api_key, api_secret = _resolve_credentials(api_key_name, private_key, require=False)
        self._supervisor = _StreamSupervisor(
            name="market-data",
            product_ids=product_ids,
            on_message=on_message,
            on_reset=on_reset,
            api_key=api_key,
            api_secret=api_secret,
            client_factory=client_factory or WSClient,
            subscribe=_subscribe_market,
        )

    def start(self) -> None:
        self._supervisor.start()

    def stop(self) -> None:
        self._supervisor.stop()


class UserStream:
    """Supervisor-owned user-channel WS (user + heartbeats).

    Requires credentials (same config constants as :class:`CoinbaseAdvanced`).
    Fails closed before the supervisor starts if keys are absent.
    """

    def __init__(
        self,
        product_ids: Sequence[str],
        on_message: OnMessage,
        *,
        on_reset: OnReset | None = None,
        api_key_name: str | None = None,
        private_key: str | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        api_key, api_secret = _resolve_credentials(api_key_name, private_key, require=True)
        self._supervisor = _StreamSupervisor(
            name="user",
            product_ids=product_ids,
            on_message=on_message,
            on_reset=on_reset,
            api_key=api_key,
            api_secret=api_secret,
            client_factory=client_factory or WSUserClient,
            subscribe=_subscribe_user,
        )

    def start(self) -> None:
        self._supervisor.start()

    def stop(self) -> None:
        self._supervisor.stop()
