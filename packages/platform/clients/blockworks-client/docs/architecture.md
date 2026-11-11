# Architecture and maintenance

`BlockworksClient` owns configuration and request lifecycle. Shared client-common
owns pooled HTTPX access and the single retry policy. Small resource namespaces
map public methods to exact pinned GET templates. `_wire.py` encodes dates,
booleans, lists, selections, and opaque path IDs and checks response essentials.
Dynamic fields remain mappings; timeseries points remain compact arrays.

`_generated.py` holds build-time route, parameter, enum, and required-series
metadata. Ordinary import and request paths do not parse OpenAPI or fetch a
catalog. No response cache, canonicalization, storage, scheduler, async layer, or
time-window splitting is supplied.

## Files

| Location | Responsibility |
| --- | --- |
| `src/blockworks_client/client.py` | Authentication, lifecycle, raw reads, decoded responses, streamed exports. |
| `src/blockworks_client/resources/` | Provider-specific method namespaces and explicit iterators. |
| `models.py`, `exceptions.py`, `_wire.py` | Stable public envelope typing, failure categories, serialization and essential checks. |
| `_generated.py`, `py.typed` | Deterministic route metadata and distributed typing marker. |
| `specs/upstream/` | Untouched public specifications. |
| `specs/manifest.json`, `specs/overrides.json` | Source URLs/hashes/date and narrowly reviewed nullability additions. |
| `tools/specs.py` | Validate local refs, apply overlays to copies, generate metadata and coverage, detect drift. |
| `tests/` | Synthetic deterministic fixtures and independent regression checks. |
| `docs/coverage.csv` | All 226 read routes mapped to public methods. |

## Update procedure

1. Fetch the five public specs and retain their original bytes; inspect the diff.
2. Check route count, parameter changes, schemas, origin, and internal references.
   The generator rejects external references and unexpected GET/write counts.
3. Review each scoped nullability overlay. Already-fixed or missing upstream
   targets fail validation instead of silently applying stale corrections.
4. Regenerate with `python tools/specs.py --retrieved-date YYYY-MM-DD` using the
   actual retrieval date, and inspect metadata/coverage changes. Unchanged snapshots
   retain the manifest date; changed bytes require the explicit date. Coverage is
   generated inventory only. Keep dated live observations out of tracked docs.
5. Run `--check`, tests, lint, type checks, wheel/sdist and isolated import checks.
6. Run a small read-only live check with your own key before choosing a package
   version.

SDK release versions and source specification hashes serve different purposes.
Neither a permissive schema nor a successful HTTP status alone proves semantic
correctness or data coverage. Keep live diagnostics out of
tracked files; tracked fixtures are synthetic.

## Shared transport changes

The additive shared options are `follow_redirects`, `request_timeout`, and retry
configuration fields `jitter`, `max_elapsed`, `extended_retry_after`. Defaults keep
injected-session settings and the basic Retry-After parsing.
Blockworks opts into finite request timeouts, disabled redirects, bounded retry
scheduling, HTTP-date Retry-After parsing, and jitter. Streaming retries only
before the response is yielded. See client-common's README for precise limits.
