"""Hermetic tests for MarketDataStream / UserStream supervisors (no network)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest
from coinbase_advanced_client import (
    CoinbaseAdvancedConfigurationError,
    MarketDataStream,
    UserStream,
)
from coinbase_advanced_client.ws import _shutdown_sdk_client

# --------------------------------------------------------------------------- #
# Stub SDK clients
# --------------------------------------------------------------------------- #


class _StubWSClient:
    """Minimal WS client stub used by the supervisor (retry=False path)."""

    instances: list[_StubWSClient] = []
    fail_open_times: int = 0
    fail_after_polls: int | None = None
    raise_on_close: bool = False

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.on_message = kwargs.get("on_message")
        self.retry = kwargs.get("retry")
        self.opened = False
        self.closed = False
        self.channels: list[tuple[str, list[str] | None]] = []
        self.polls = 0
        self.thread = threading.Thread(target=lambda: None, name="stub-sdk")
        # already finished thread (join is a no-op)
        self.thread.start()
        self.thread.join()
        self.loop = None
        _StubWSClient.instances.append(self)

    def open(self) -> None:
        if _StubWSClient.fail_open_times > 0:
            _StubWSClient.fail_open_times -= 1
            raise RuntimeError("simulated open failure")
        self.opened = True

    def close(self) -> None:
        self.closed = True
        if _StubWSClient.raise_on_close:
            raise RuntimeError("already closed")

    def ticker(self, product_ids: list[str]) -> None:
        self.channels.append(("ticker", list(product_ids)))

    def user(self, product_ids: list[str]) -> None:
        self.channels.append(("user", list(product_ids)))

    def heartbeats(self) -> None:
        self.channels.append(("heartbeats", None))

    def raise_background_exception(self) -> None:
        self.polls += 1
        if _StubWSClient.fail_after_polls is not None and self.polls >= _StubWSClient.fail_after_polls:
            # One-shot failure for this client instance.
            _StubWSClient.fail_after_polls = None
            raise RuntimeError("simulated remote close")


class _PinnedSDKClient(_StubWSClient):
    """Stub that mirrors the pinned SDK's close-raises-when-loop-gone behavior."""

    def close(self) -> None:
        # First close succeeds; subsequent close raises like the real SDK.
        if self.closed:
            raise RuntimeError("Event loop is not running.")
        self.closed = True


def _reset_stub_state() -> None:
    _StubWSClient.instances.clear()
    _StubWSClient.fail_open_times = 0
    _StubWSClient.fail_after_polls = None
    _StubWSClient.raise_on_close = False


@pytest.fixture(autouse=True)
def _clean_stub() -> Any:
    _reset_stub_state()
    yield
    _reset_stub_state()


# --------------------------------------------------------------------------- #
# MarketDataStream credentials
# --------------------------------------------------------------------------- #


def test_market_data_allows_unauthenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINBASE_ADVANCED_API_KEY_NAME", raising=False)
    monkeypatch.delenv("COINBASE_ADVANCED_PRIVATE_KEY", raising=False)
    msgs: list[dict[str, Any]] = []
    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=msgs.append,
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not _StubWSClient.instances:
        time.sleep(0.02)
    assert _StubWSClient.instances
    client = _StubWSClient.instances[0]
    assert client.retry is False
    assert client.kwargs.get("api_key") is None
    assert client.kwargs.get("api_secret") is None
    stream.stop()


def test_market_data_passes_keys_when_present() -> None:
    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not _StubWSClient.instances:
        time.sleep(0.02)
    assert _StubWSClient.instances[0].kwargs["api_key"] == "k"
    assert _StubWSClient.instances[0].kwargs["api_secret"] == "s"
    stream.stop()


def test_market_data_partial_credentials_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COINBASE_ADVANCED_API_KEY_NAME", raising=False)
    monkeypatch.delenv("COINBASE_ADVANCED_PRIVATE_KEY", raising=False)
    with pytest.raises(CoinbaseAdvancedConfigurationError, match="incomplete"):
        MarketDataStream(
            product_ids=["BTC-USDC"],
            on_message=lambda _m: None,
            api_key_name="k",
            client_factory=_StubWSClient,
        )


def test_user_stream_reads_environment_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINBASE_ADVANCED_API_KEY_NAME", "fake-key-name")
    monkeypatch.setenv("COINBASE_ADVANCED_PRIVATE_KEY", "fake-private-key")
    stream = UserStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        client_factory=_StubWSClient,
    )

    assert stream._supervisor._api_key == "fake-key-name"
    assert stream._supervisor._api_secret == "fake-private-key"


# --------------------------------------------------------------------------- #
# Subscribe + reconnect restores heartbeats + on_reset
# --------------------------------------------------------------------------- #


def test_market_data_subscribes_ticker_and_heartbeats() -> None:
    stream = MarketDataStream(
        product_ids=["BTC-USDC", "ETH-USDC"],
        on_message=lambda _m: None,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not (_StubWSClient.instances and _StubWSClient.instances[0].channels):
        time.sleep(0.02)
    client = _StubWSClient.instances[0]
    assert ("ticker", ["BTC-USDC", "ETH-USDC"]) in client.channels
    assert ("heartbeats", None) in client.channels
    stream.stop()


def test_user_stream_subscribes_user_and_heartbeats() -> None:
    stream = UserStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not (_StubWSClient.instances and _StubWSClient.instances[0].channels):
        time.sleep(0.02)
    client = _StubWSClient.instances[0]
    assert ("user", ["BTC-USDC"]) in client.channels
    assert ("heartbeats", None) in client.channels
    stream.stop()


def test_reconnect_restores_heartbeats_and_fires_on_reset() -> None:
    resets = threading.Event()
    reset_count = {"n": 0}

    def on_reset() -> None:
        reset_count["n"] += 1
        resets.set()

    _StubWSClient.fail_after_polls = 2
    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        on_reset=on_reset,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    assert resets.wait(timeout=5.0), "on_reset was not fired after simulated remote close"
    # Wait for a second client instance with heartbeats resubscribed.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and len(_StubWSClient.instances) < 2:
        time.sleep(0.02)
    assert len(_StubWSClient.instances) >= 2
    second = _StubWSClient.instances[1]
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not second.channels:
        time.sleep(0.02)
    assert ("heartbeats", None) in second.channels
    assert ("ticker", ["BTC-USDC"]) in second.channels
    assert reset_count["n"] >= 1
    stream.stop()


def test_stop_terminates_without_leaked_threads() -> None:
    before = {t.ident for t in threading.enumerate()}
    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not _StubWSClient.instances:
        time.sleep(0.02)
    stream.stop()
    # Supervisor thread must be gone; no coinbase-* threads remain.
    leftover = [
        t
        for t in threading.enumerate()
        if t.ident not in before and t.is_alive() and (t.name or "").startswith("coinbase-")
    ]
    assert leftover == []


def test_forwards_parsed_json_messages() -> None:
    received: list[dict[str, Any]] = []
    got = threading.Event()

    def on_message(msg: dict[str, Any]) -> None:
        received.append(msg)
        got.set()

    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=on_message,
        api_key_name="k",
        private_key="s",
        client_factory=_StubWSClient,
    )
    stream.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not _StubWSClient.instances:
        time.sleep(0.02)
    client = _StubWSClient.instances[0]
    assert client.on_message is not None
    client.on_message(json.dumps({"channel": "ticker", "sequence_num": 1, "events": []}))
    assert got.wait(timeout=2.0)
    assert received[0]["channel"] == "ticker"
    assert received[0]["sequence_num"] == 1
    stream.stop()


def test_fresh_client_per_reconnect_and_tolerant_shutdown() -> None:
    """Pinned-SDK-style: remote close, close may raise; no leaked clients/threads."""
    _StubWSClient.fail_after_polls = 1
    _StubWSClient.raise_on_close = True
    stream = MarketDataStream(
        product_ids=["BTC-USDC"],
        on_message=lambda _m: None,
        api_key_name="k",
        private_key="s",
        client_factory=_PinnedSDKClient,
    )
    stream.start()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and len(_StubWSClient.instances) < 2:
        time.sleep(0.02)
    assert len(_StubWSClient.instances) >= 2
    # First instance was shut down (closed flag set despite raise_on_close path).
    assert _StubWSClient.instances[0].closed is True
    stream.stop()
    assert all(c.closed for c in _StubWSClient.instances)


def test_shutdown_sdk_client_tolerates_already_closed() -> None:
    client = _PinnedSDKClient(on_message=lambda _m: None, retry=False)
    client.closed = True  # pretend already closed
    _shutdown_sdk_client(client)  # must not raise
