# blockworks-client

Synchronous, read-only access to all 226 documented Blockworks GET routes. The four
Watchlists mutations are excluded. Python 3.12 is supported.

Agents: start with [docs/llms.txt](docs/llms.txt) for the SDK documentation index and official upstream links.

## Installation and credentials

From the repository root:

```bash
uv sync --frozen --inexact --package blockworks-client --group dev
uv run --package blockworks-client python your_program.py  # BLOCKWORKS_API_KEY in the environment
```

`BlockworksClient()` reads `BLOCKWORKS_API_KEY` when constructed. An explicit
`api_key=` takes precedence. Set the key in the environment, never on the
command line. The SDK never writes credentials.
Standalone consumers can install the built wheel together with `client-common`.
Runtime dependencies are HTTPX and client-common; client-common also brings Polars
transitively. Dataframe conversion is not required. OpenAPI schema validation is a
development dependency only.

## Quickstart

```python
from blockworks_client import BlockworksClient

with BlockworksClient() as client:
    assets = client.tabular.list(
        "assets", page_size=1, selections=["assetID", "name", "symbol"]
    )
    asset_id = assets.body["data"][0]["assetID"]
    history = client.timeseries.single(
        "asset-price", "1d", asset_id, timeframe="7d", selections=["close"]
    )
    print(history.body["data"]["point_schema"])
    print(history.body["data"]["points"])
```

Granularity belongs in the path. `timeframe` is a query window and cannot be
combined with `start` or `end`. Explicit windows accept strings, dates, aware
datetimes, and Unix-second integers. Naive datetimes are rejected. Bucket rounding
is preserved; the SDK does not shift, stitch, clip, or fill provider data.

## Response and lifecycle

Each resource call returns `BlockworksResponse` with `body`, `status`, `headers`,
and `request_id`. `body` retains the provider's complete envelope, unknown fields,
explicit nulls, dynamic rows, and compact timeseries point arrays. Use the returned
`point_schema` object's `field` order to interpret each point. Empty data is valid.
Stable envelope TypedDicts are supplied as opt-in annotations, and the wheel includes `py.typed`.

The client reuses pooled connections. Context manager exit closes its own session;
an injected `httpx.Client` remains owned by its caller. An injected session must
have the exact `https://api.blockworks.com` origin. The SDK applies its own finite
request timeout and disables redirects without mutating that session's defaults.
Requests remain bound to the Blockworks origin even if the borrowed base URL changes.
Injected query defaults, authentication, cookies, and credential headers are rejected
at construction and before each request. Do not mutate a borrowed session concurrently
or use hooks/transports that rewrite requests; these are trusted caller code.

Constructor options: `timeout=20.0`, `max_attempts=3`, `max_elapsed=60.0`, and
`http_client=None`. `max_elapsed` bounds retry scheduling, including sleep delays;
it is not a hard wall-clock cancellation deadline. HTTPX timeouts separately bound
network operations. One shared layer retries eligible GET failures with jitter
and Retry-After handling. Permission failures are not retried.

## Resource methods

| Namespace | Methods | Query convention |
| --- | --- | --- |
| `tabular` | `catalog`, `list`, `get`, `iter_pages`, `export_list` | Model slug; `filters` contains exact provider names such as `slugEq`; conveniences include `page_size`, `sort_by`, `sort_direction`, `selections`. |
| `timeseries` | `catalog`, `batch`, `single`, `iter_batches`, `export_batch`, `export_single` | Model slug and granularity; optional dates/timeframe, selections, bounds; explicit series limit ten. |
| `charts` | `list`, `data` | `page`, `limit`, `search`; chart data also has `select`, `order_by`, `order_dir`. |
| `unlocks` | `assets`, `allocations`, `events`, `unlocks`, `vesting_schedule` | Exact provider names including `assetIDs`, `startTime`, `endTime`, `unlockType`; `unlocks` requires `interval`. |
| `monitoring` | `categories`, `developments`, `development`, `events`, `event`, `views`, `view`, `view_developments`, `view_events`, `all_view_developments`, `all_view_events` | Exact native query names through keyword arguments, including `assetIds`, `intelCategories`, `verified`, `minimumImportance`, `start`, `end`. |
| `watchlists` | `list`, `get` | Read-only account watchlists. |

See [coverage.csv](docs/coverage.csv) for every route-to-method mapping. Native
query names are validated against the pinned spec. Selections and list filters
are encoded as comma-separated values. False and zero values are preserved.

`list`, `get`, `batch`, and `single` each make one request. `iter_pages` is available
only for tabular data with verified total-page metadata. It is sequential, detects
repeated pages, and raises when `max_pages` truncates a result. It cannot promise
snapshot consistency while provider data changes. Empty nonterminal pages raise.
The repeated-page check compares projected payloads; include an identifying field
in selections to distinguish otherwise identical pages. `iter_batches` chunks explicit
series into groups of at most ten and rejects duplicates. It snapshots the ID
sequence when iteration starts, before making its first request. Unlocks has no paginator;
its `page` and `limit` are passed through as given.

## Raw responses and streamed exports

```python
with BlockworksClient() as client:
    raw = client.get_raw("/query/tabular/catalog", params={"publicOnly": True})
    print(raw.status_code, len(raw.content))
    with client.stream("/query/tabular/assets", params={"pageSize": 2, "acceptFormat": "csv"}) as response:
        for chunk in response.iter_bytes():
            consume(chunk)
```

`stream` genuinely streams and closes on early exit. `export_to`, `export_list`,
`export_batch`, and `export_single` stream native CSV or JSONL to a caller-provided
binary handle or explicit path and return bytes written. Binary handles must
return a positive byte count from `write`; partial writes are handled. Files open
only after an HTTP success response. Mid-stream network or destination failures
leave partial output at the caller's destination and raise; streams never restart
after yielding bytes. The caller owns any atomic replacement or cleanup policy.

Decoded resource methods reject `acceptFormat`; use the export methods for CSV/JSONL.
Tabular reads and exports apply the same validation to native filters and convenience
arguments, including duplicate arguments and page-size limits.

Raw methods are GET-only and origin-relative. Absolute URLs, traversal, embedded
queries, and redirects are rejected. Queries go through `params`, and callers
cannot override the authentication header.

## Errors and compatibility

Public exceptions distinguish configuration, transport, API, decoding, and
pagination failures. API errors expose a status, bounded safe detail, and request
ID without credentials or full request dumps. Unmapped statuses omit provider prose.
`BlockworksAPIError.retry_after` is a normalized, bounded numeric-seconds or HTTP-date
string, or `None` for missing/invalid headers. It preserves cooldown information after
retries finish; it does not schedule another request. HTTP 403 is reported as
"access forbidden" and is not automatically classified as a bad key.

[architecture.md](docs/architecture.md) describes maintenance and ownership.

## Development checks

From the repository root:

```bash
uv sync --frozen --all-packages --group dev
uv run python packages/platform/clients/blockworks-client/tools/specs.py --check
uv run pytest packages/platform/clients/blockworks-client/tests packages/platform/clients/client-common/tests -q
uv run ruff check packages/platform/clients/blockworks-client packages/platform/clients/client-common
uv build --package blockworks-client
```

The spec tool performs no network requests. Update the public snapshots explicitly,
review changes and scoped overlays, regenerate metadata, then run the deterministic
checks and a small read-only live check with your own key.
