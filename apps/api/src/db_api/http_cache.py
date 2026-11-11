"""HTTP cache-control policy for the read-only DB API.

The lake behind this service can be re-synced at any time and the operator's
freshness gesture is a browser reload, so dataset payloads must never be
served from a browser TTL cache. Policy, applied to GET 200 responses only:

- ``no-store`` for ``/health`` and prefixes extensions register for direct-upstream
  reads: probes and explicitly uncached data must always observe the live source.
- ``private, max-age=60`` for discovery reads whose staleness the web client
  already tolerates for 60 seconds: catalog root/logical/browse listings,
  catalog markdown/stats/overview, docs tree and pages, dataset schema
  listings, and the features browser tree and document previews.
- ``private, no-cache`` (revalidate every use) for every other ``/api`` GET,
  including all dataset query/preview/stats/arrow and chart/profile payloads.

Explicit endpoint ``no-store`` directives are preserved.

Non-GET requests, non-200 responses, and paths outside ``/api`` and
``/health`` never receive cache headers.

USAGE:
    app.add_middleware(CacheControlMiddleware)
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DISCOVERY_PATHS = frozenset(
    {
        "/api/catalog",
        "/api/catalog/logical",
        "/api/catalog/stats",
        "/api/catalog/overview",
        "/api/docs/tree",
        "/api/features/browser",
        "/api/features/browser-stats",
    }
)
_DISCOVERY_PREFIXES = (
    "/api/catalog/browse/",
    "/api/catalog/markdown/",
    "/api/docs/page/",
    "/api/features/browser/",
    "/api/features/markdown/",
    "/api/features/structured/",
)


_no_store_prefixes: tuple[str, ...] = ()


def register_no_store_prefix(prefix: str) -> None:
    """Mark an extension's direct-upstream routes ``no-store``."""
    global _no_store_prefixes
    if prefix not in _no_store_prefixes:
        _no_store_prefixes = (*_no_store_prefixes, prefix)


def cache_control_for(path: str) -> str | None:
    """Return the Cache-Control value for a GET request path, if any."""
    if path == "/health" or path.startswith(_no_store_prefixes):
        return "no-store"
    if not path.startswith("/api/"):
        return None
    if path in _DISCOVERY_PATHS or path.startswith(_DISCOVERY_PREFIXES):
        return "private, max-age=60"
    segments = path.split("/")
    if len(segments) >= 6 and segments[2] == "datasets" and segments[4] == "schema":
        return "private, max-age=60"
    return "private, no-cache"


class CacheControlMiddleware:
    """Attach Cache-Control headers to GET 200 responses per module policy."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return
        cache_control = cache_control_for(scope["path"])
        if cache_control is None:
            await self.app(scope, receive, send)
            return

        async def send_with_cache_control(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                headers = MutableHeaders(scope=message)
                if headers.get("Cache-Control") != "no-store":
                    headers["Cache-Control"] = cache_control
            await send(message)

        await self.app(scope, receive, send_with_cache_control)
