"""FastAPI application factory for the public core and optional extensions.

USAGE::

    from db_api.main import app
    public_app = create_app(load_extensions=False)
    isolated_app = create_app(extension_root=Path("/missing/extensions"))
"""

from contextlib import asynccontextmanager
from pathlib import Path

from data.query import QueryError, QueryPathError, QueryValidationError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from .catalog_labels import load_catalog_labels
from .config import settings
from .dataset_index import prewarm_parquet_indexes
from .entity_labels import configure_entity_labels, load_entity_label_rules
from .extensions import load_extensions as register_extensions
from .http_cache import CacheControlMiddleware
from .origin_guard import OriginGuardMiddleware
from .routers import (
    backtest_engine,
    backtest_updates,
    backtests,
    benchmarks,
    catalog,
    datasets,
    docs,
    features,
    ml_engine,
    portfolio_diagnostics,
    production,
    research,
    signals,
    strategy_versions,
)

# --------------------------------------------------------------------------- #
# Stable handlers
# --------------------------------------------------------------------------- #


def query_error_handler(_request: Request, exc: QueryError) -> JSONResponse:
    """Map query-layer errors to stable API responses."""
    if isinstance(exc, QueryPathError):
        detail = str(exc)
        return JSONResponse(
            status_code=403 if detail == "Access denied" else 404,
            content={"detail": detail},
        )
    if isinstance(exc, QueryValidationError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Dataset query failed"})


def health_check() -> dict[str, object]:
    """Return API health and DB root visibility."""
    return {
        "status": "healthy",
        "db_root": str(settings.db_root),
        "db_exists": settings.db_root.exists(),
    }


# --------------------------------------------------------------------------- #
# Application construction
# --------------------------------------------------------------------------- #

DEFAULT_EXTENSION_ROOT = Path(__file__).resolve().parents[2] / "extensions"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prewarm shared read-only discovery indexes for predictable first requests."""
    prewarm_parquet_indexes(settings.db_root)
    yield


def create_app(
    *,
    load_extensions: bool = True,
    extension_root: Path | None = None,
) -> FastAPI:
    """Create the DB API, optionally loading extensions from an explicit root."""
    application = FastAPI(
        title="quant-factory DB API",
        description="Read-only API over the quant-factory data query layer.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(CacheControlMiddleware)
    application.add_middleware(OriginGuardMiddleware, allowed_origins=settings.cors_origins)
    application.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
    application.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
    application.include_router(backtest_engine.router, prefix="/api/backtest-engine", tags=["backtest-engine"])
    application.include_router(backtest_updates.router, prefix="/api/backtest-updates", tags=["backtest-updates"])
    application.include_router(benchmarks.router, prefix="/api/benchmarks", tags=["benchmarks"])
    application.include_router(features.router, prefix="/api/features", tags=["features"])
    application.include_router(ml_engine.router, prefix="/api/ml-engine", tags=["ml-engine"])
    application.include_router(production.router, prefix="/api/production", tags=["production"])
    application.include_router(signals.router, prefix="/api/signals", tags=["signals"])
    application.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
    application.include_router(docs.router, prefix="/api/docs", tags=["docs"])
    application.include_router(
        portfolio_diagnostics.router, prefix="/api/portfolio-diagnostics", tags=["portfolio-diagnostics"]
    )
    application.include_router(research.router, prefix="/api/research", tags=["research"])
    application.include_router(strategy_versions.router, prefix="/api/strategy-versions", tags=["strategy-versions"])
    application.add_exception_handler(QueryError, query_error_handler)
    application.add_api_route("/health", health_check, methods=["GET"])

    if load_extensions:
        root = DEFAULT_EXTENSION_ROOT if extension_root is None else extension_root
        application.state.catalog_labels = load_catalog_labels(root / "catalog-labels.json")
        configure_entity_labels(load_entity_label_rules(root / "entity-labels.json"))
        application.state.loaded_extensions = register_extensions(application, root)
    else:
        application.state.catalog_labels = {}
        configure_entity_labels(())
        application.state.loaded_extensions = ()
    return application


# Importing the public factory must not discover installed extensions. Python's
# module attribute hook preserves ``db_api.main:app`` and explicit app imports
# while constructing the full application only when that attribute is requested.
_default_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Create the production application lazily for the stable ``app`` entry point."""
    global _default_app
    if name != "app":
        raise AttributeError(name)
    if _default_app is None:
        _default_app = create_app()
    return _default_app


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """Run the API server on the configured host and port."""
    import argparse

    import uvicorn

    argparse.ArgumentParser(
        description="Serve the read-only DB API (host, port and debug come from settings)."
    ).parse_args()

    uvicorn.run(
        "db_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
