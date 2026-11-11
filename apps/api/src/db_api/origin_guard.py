"""Reject state-changing requests sent by other websites.

A browser attaches ``Origin`` to every cross-site POST/PUT/PATCH/DELETE, and CORS
does not stop a "simple" request from reaching the server: any open web page could
otherwise start a backtest update or a catalog refresh on this local API. This guard
lets an unsafe request through only when it has no ``Origin`` (curl, scripts,
same-process clients) or its ``Origin`` is local: a loopback host, a ``*.localhost``
dev host, or one of ``settings.cors_origins``. Safe methods pass untouched.

USAGE:
    application.add_middleware(OriginGuardMiddleware, allowed_origins=settings.cors_origins)
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# --------------------------------------------------------------------------- #
# Origin policy
# --------------------------------------------------------------------------- #

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_local_origin(origin: str, allowed_origins: Iterable[str] = ()) -> bool:
    """Return whether ``origin`` is a configured origin or a local dev host."""
    if origin in set(allowed_origins):
        return True
    parts = urlsplit(origin)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not host:
        return False
    return host in _LOOPBACK_HOSTS or host.endswith(".localhost")


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #


class OriginGuardMiddleware:
    """403 for unsafe-method HTTP requests whose ``Origin`` is not local."""

    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str] = ()) -> None:
        self.app = app
        self.allowed_origins = tuple(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in _SAFE_METHODS:
            origin = next(
                (value.decode("latin-1") for key, value in scope["headers"] if key == b"origin"),
                None,
            )
            if origin is not None and not is_local_origin(origin, self.allowed_origins):
                response = JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
