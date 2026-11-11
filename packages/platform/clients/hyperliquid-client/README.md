# Hyperliquid client

This package is the only quant-factory boundary allowed to import the official
`hyperliquid-python-sdk`. It exposes explicit default-DEX and configured HIP-3
`/info` reads, a supervised read-only stream, allowlisted ALO/IOC limit orders,
and cancellation by provider `oid` or caller-owned `cloid`.

It deliberately does not expose transfers, withdrawals, wallet approval,
subaccount management, leverage or margin changes, SDK market helpers, a raw
`Info` or `Exchange`, or arbitrary `/info` or `/exchange` calls.

```python
from hyperliquid_client import HyperliquidClientConfig, HyperliquidReadClient

client = HyperliquidReadClient(
    HyperliquidClientConfig(
        network="testnet",
        account_address="0x1111111111111111111111111111111111111111",
        perp_dexs=("dexa", "dexb"),
    )
)
meta, contexts = client.meta_and_asset_contexts("dexa")
```

Read-only construction does not resolve a private key. Mutating construction uses the separate
`HyperliquidClient` type and requires an activation-bound expected API-wallet address and a key
supplied as `HYPERLIQUID_AGENT_PRIVATE_KEY` in the environment. Placement also requires the exact
`HYPERLIQUID_TRADING_ENABLED=1` gate. Do not put secret values in Git, argv,
logs, Markdown, chat, or browser automation.

Builder-perpetual symbols are always fully qualified, such as `dexa:TOKN`.
Unqualified builder symbols and DEXes absent from `perp_dexs` fail before
network access. The existing default-DEX and mandatory-cloid
`place_limit_ioc` method remains source-compatible.

Run the hermetic package tests from the repository root:

```bash
uv run --project packages/platform/clients/hyperliquid-client pytest \
  packages/platform/clients/hyperliquid-client/tests -q
```

### Unsigned request timeout

`HyperliquidReadClient(..., request_timeout_s=<positive finite seconds>)` forwards
an explicit HTTP timeout to the official SDK's read-only `Info` instance. Omission
preserves the SDK's existing timeout behavior for current consumers. Supervised
consumers should supply their own timeout and independently check total snapshot
age; an HTTP timeout is not a hard wall-clock guarantee for a multi-call capture.
The option does not construct a signing client or change trading gates.

### Explicit fast book feed

`StreamSubscription("l2Book", coin="dexa:TOKN", fast=True)` requests the provider's
five-level fast book. Omit `fast` to preserve the existing provider-default
subscription. The option is rejected on other channels. Consumers must use only
received depth and retain their own freshness gates; fast mode is not a latency
guarantee. See the official [subscription contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions).
