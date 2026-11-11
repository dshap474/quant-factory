# coinbase-advanced-client

- Thin capability-limited facade over the official `coinbase-advanced-py`
  SDK; no public RESTClient escape hatch. Read
  `packages/platform/AGENTS.md` (trading gates, under "Authority and validation") before touching
  the gate or quote logic.
- Orders trade `-USDC` quoted pairs only, never `-USD`: Coinbase's funds check
  is literal per currency, even though e.g. BTC-USDC aliases the same BTC-USD book.
  Enforced by `_ALLOWED_QUOTE = "USDC"` in `api.py`; never weaken or bypass.
- Scope the API key to one dedicated portfolio; other portfolios then 403.
- Advanced Trade has NO sandbox — `preview_order` is the only dry run; the
  preview body takes no `client_order_id`; previews enforce per-product
  min-size/precision beyond `base_increment`.
- The trading gate `COINBASE_ADVANCED_TRADING_ENABLED` is an import-time
  snapshot via `config` — set it in the launching process env; setting it
  after import does nothing.
