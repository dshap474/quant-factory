# fred-client

Thin client for the St. Louis Fed FRED and ALFRED APIs.

`get_release_dates(release_id, ...)` lists a release's publication dates (future scheduled dates with
`include_release_dates_with_no_data=True`). `get_series_observations(..., output_type=4)` over the all-time
realtime window (`1776-07-04`..`9999-12-31`) returns ALFRED first releases: each observation's first-print
value with `realtime_start` = the date it was first published.

`get_series_observations_public(...)` reads FRED's public graph CSV feed without
an API key. It returns the same observation shape as the authenticated method
and does not cache or persist responses. Its User-Agent is
`<user_agent> python-httpx/<version>`; requests whose User-Agent omits the HTTP
library token have been observed to stall until timeout. The CSV feed carries no
realtime period, no series metadata and omits missing (`.`) days. FRED's terms of
use (https://fred.stlouisfed.org/legal/) govern the data, including third-party
series that carry their own copyright; check them before redistributing it.

By default, `FredClient()` lazily reads `FRED_API_KEY` when the first authenticated request is
made. Provide credentials through the process environment.
Offline tests may inject `api_key=` explicitly.
