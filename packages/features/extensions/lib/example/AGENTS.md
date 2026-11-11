# example feature family

- Reporting clock: inputs come from `example.prices.derived_1d`, stamped at availability; row `T` is the
  completed daily bar for `T`. This family adds no lag.
- `close` is Yahoo's auto-adjusted close, so past levels move when later dividends and splits arrive
  (see the data example README). `ret_1d` and `mom_30d` are unaffected between adjustments.
- Momentum windows count bars per asset, not calendar days; assets with different trading calendars
  (BTC trades every day, ETFs do not) cover different calendar spans for the same window.
- Blocks: `close` is `price`; `ret_*` and `mom_*` are `returns` (declared in `runner.py`).
