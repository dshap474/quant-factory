# client-common

Shared `HTTPClient`/`RetryConfig` transport and polars frame helpers (`records_to_frame`, `csv_text_to_frame`, `key_value_frame`) for platform clients to build on. No caches, paths, or file writes.

`HTTPClient.stream_get()` is a context manager for streamed GET responses. It
closes responses on early exit and retries only before yielding. Once caller code
can consume bytes, interrupted reads propagate and are never restarted.

Optional `follow_redirects=False` overrides both owned and injected sessions per
request. The default `None` preserves injected session behavior and the existing
owned-session redirect default. `request_timeout=` explicitly overrides request
and stream timeouts without mutating injected sessions; its default leaves them
unchanged.

`RetryConfig` retains its original defaults. Opt-in `jitter` adds a random fraction
of exponential delay; `extended_retry_after=True` accepts HTTP dates and decimal
seconds. `max_elapsed` bounds whether another attempt and sleep may be scheduled.
It is a retry scheduling budget, not a hard total wall-clock deadline; individual
HTTPX network operations still use configured timeouts. Long streams are governed
by their read timeouts and caller lifecycle.
