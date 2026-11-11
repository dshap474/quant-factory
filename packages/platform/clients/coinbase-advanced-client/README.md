# coinbase-advanced-client

Thin auth/config wrapper over the official, exactly pinned
[`coinbase-advanced-py`](https://github.com/coinbase/coinbase-advanced-py) SDK
`1.8.4` (Advanced Trade REST + WebSocket).

**Boundary:** authenticated clients read `COINBASE_ADVANCED_API_KEY_NAME` and
`COINBASE_ADVANCED_PRIVATE_KEY`, own one
`coinbase.rest.RESTClient`, and exposes read / preview / **hard-gated** placement
helpers plus supervisor-owned WebSocket streams.
Intent → payload shaping is left
to the caller's venue adapter. Advanced Trade has **no stateful trading sandbox**; the official sandbox
returns static, predefined responses only.

## Trading surface + gate semantics

| Method | Gate | Notes |
|--------|------|--------|
| Read / list / get / fills / portfolios / fees / BBO | none | passthrough |
| `preview_order` | none | estimate only; never places |
| `cancel_orders` | **none** | always allowed (risk-reducing) |
| `create_order` | **`COINBASE_ADVANCED_TRADING_ENABLED == "1"`** | first statement; else `CoinbaseAdvancedTradingDisabledError` |

Additional `create_order` local guards (before the SDK is called):

- **`client_order_id` required** — empty/falsey is rejected so the SDK's uuid4
  fallback cannot silently drop the duplicate-order safeguard.
- **USDC quote only** — `product_id` must have quote leg `USDC` (e.g. `BTC-USDC`).

Related config:

- `COINBASE_ADVANCED_TRADING_ENABLED` — default empty/falsy; set to `1` to arm placement.
  `create_order` enforces it (see the table above).
- `COINBASE_ADVANCED_PORTFOLIO_UUID` — optional expected portfolio UUID, exposed as
  `configured_portfolio_uuid` for a caller's own venue adapter to check.

**Not wrapped:** `edit_order`, move_funds / transfer, `get_product_book`.


## Public product catalog

The credential-free catalog client follows Coinbase cursor pagination and
deduplicates repeated product IDs:

```python
from coinbase_advanced_client import CoinbaseAdvancedPublic

client = CoinbaseAdvancedPublic()
spot = client.list_products(product_type="SPOT")
futures = client.list_futures()
```

Print a sorted catalog from the command line:

```bash
uv run qf-coinbase-products --product-type SPOT --head 10 --descending
uv run qf-coinbase-products --product-type FUTURE --head 10 --descending
```

Public discovery does not prove that the authenticated account may trade every
returned product. Use authenticated `CoinbaseAdvanced.get_products(...,
get_tradability_status=True)` for that separate check.

## Quick start

```python
from coinbase_advanced_client import CoinbaseAdvanced

client = CoinbaseAdvanced()  # paired credentials from the environment
accounts = client.get_accounts(limit=250)
product = client.get_product("BTC-USDC", get_tradability_status=True)
bbo = client.get_best_bid_ask(product_ids=["BTC-USDC"])
fees = client.get_transaction_summary()
perms = client.get_api_key_permissions()
preview = client.preview_order(
    product_id="BTC-USDC",
    side="BUY",
    order_configuration={"market_market_ioc": {"base_size": "0.0001"}},
)
# typed SDK response objects
```


Or pass credentials explicitly (never log key material):

```python
client = CoinbaseAdvanced(api_key_name="organizations/.../apiKeys/...", private_key="-----BEGIN ...")
```

## WebSocket streams

`MarketDataStream` (public ticker + heartbeats) and `UserStream` (user + heartbeats)
own reconnection with `retry=False` on the SDK. Each builds a **fresh** SDK client
per connection attempt, resubscribes **all** channels (including heartbeats), and
fires `on_reset` on failure. Credential resolution matches the REST facade;
market data may run unauthenticated without credentials, while user stream fails
closed without keys.

```python
from coinbase_advanced_client import MarketDataStream, UserStream

def on_msg(msg: dict) -> None:
    print(msg.get("channel"), msg.get("sequence_num"))

md = MarketDataStream(product_ids=["BTC-USDC"], on_message=on_msg, on_reset=lambda: print("reset"))
md.start()
# ...
md.stop()
```

## Dry run (preview only)

From the monorepo root (workspace root venv resolves all members):

```bash
uv run python packages/platform/clients/coinbase-advanced-client/scripts/dry_run.py
```

Steps: construct client → list non-zero balances (no UUIDs/keys) → fetch
`BTC-USDC` → size a ~$0.01 market buy →
`preview_order` (fails unless `errs` is explicitly empty and totals are
present). **No orders are placed.**

## Tests

```bash
uv run --project packages/platform/clients/coinbase-advanced-client \
  pytest packages/platform/clients/coinbase-advanced-client/tests -q

# live smoke (real keys; read-only + gate-refusal proof)
COINBASE_ADVANCED_LIVE=1 uv run --project packages/platform/clients/coinbase-advanced-client \
    pytest packages/platform/clients/coinbase-advanced-client/tests -m live -q
```
