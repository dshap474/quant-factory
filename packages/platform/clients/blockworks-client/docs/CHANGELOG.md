# Changelog

## Unreleased

Re-pinned the data-api spec (retrieved 2026-10-13): 226 GET routes, adding tabular
`lending-market-{financials,flows,interest-rates,liquidations}`, `project-tokens`, `tokens` and
`rwa-spot-dex-segments`, plus the matching timeseries and `rwa-spot-dex-activity`.

Re-pinned the data-api spec (retrieved 2026-10-12): 205 GET routes, adding tabular
`markets` and `lending-market-balances` plus timeseries `token-unlocks` and
`lending-market-balances`.

## 0.1.0

Initial synchronous read-only client: 198 pinned GET routes, resource namespaces,
compact typed envelopes, explicit pagination/series chunking, pooled shared
transport, safe errors, and streamed native exports. Includes public spec snapshots,
scoped nullability corrections, and deterministic generation.
