# hyperliquid-client

- Thin facade over the official `hyperliquid-python-sdk`. Read
  `packages/platform/AGENTS.md` (trading gates, under "Authority and validation") before touching
  the gate logic.
- The trading gate `HYPERLIQUID_TRADING_ENABLED` is read from `os.environ`
  LIVE at each order submit (`client.py`) — unlike Coinbase Advanced's
  import-time snapshot. The difference is deliberate; do not harmonize
  without operator direction.
- Signing uses `HYPERLIQUID_AGENT_PRIVATE_KEY` (an agent wallet, not the
  master key), read only from the environment.
