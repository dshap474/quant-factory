"""Dataset query endpoints backed by `data.query`."""

from __future__ import annotations

from data.query import (
    DatasetScope,
    ParquetQuery,
    QueryResult,
    count_parquet_rows,
    get_parquet_metadata,
    numeric_stats,
    preview_parquet,
    query_parquet,
    to_arrow_ipc_bytes,
)
from fastapi import APIRouter, HTTPException, Query, Request, Response

from ..config import settings
from ..entity_labels import page_labels
from ..responses import polars_json_response

router = APIRouter()


@router.get("/{scope}/schema/{path:path}")
def get_schema(request: Request, scope: DatasetScope, path: str) -> dict[str, object]:
    """Return parquet row count and schema without loading rows."""
    _reject_removed_backend_param(request)
    metadata = get_parquet_metadata(scope=scope, path=path, db_root=settings.db_root)
    return {
        "scope": metadata.scope,
        "path": metadata.path,
        "total_rows": metadata.total_rows,
        "schema": [
            {"name": column.name, "dtype": column.dtype}
            for column in metadata.columns
        ],
    }


@router.get("/{scope}/preview/{path:path}")
def preview_dataset(
    request: Request,
    scope: DatasetScope,
    path: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> Response:
    """Return one page from a parquet dataset."""
    _reject_removed_backend_param(request)
    result = preview_parquet(
        scope=scope,
        path=path,
        page=page,
        page_size=page_size,
        db_root=settings.db_root,
    )

    total_pages = max(1, (result.metadata.total_rows + page_size - 1) // page_size)
    page = min(page, total_pages)
    return polars_json_response({
        "scope": result.metadata.scope,
        "path": result.metadata.path,
        "total_rows": result.metadata.total_rows,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "returned_rows": result.returned_rows,
        "backend": result.backend,
        "rows": result.frame,
    }, df_key="rows")


@router.get("/{scope}/query/{path:path}")
def query_dataset(
    request: Request,
    scope: DatasetScope,
    path: str,
    columns: str | None = Query(None, description="Comma-separated columns to project"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    time_column: str = Query("timestamp"),
    entity_column: str | None = Query(None),
    entity_value: list[str] | None = Query(None),
    limit: int | None = Query(1000, ge=0, le=100_000),
    offset: int = Query(0, ge=0),
    order_by: str | None = Query(None),
    descending: bool = Query(False),
) -> Response:
    """Run a bounded projected parquet query."""
    _reject_removed_backend_param(request)
    query_request = _build_query(
        scope=scope,
        path=path,
        columns=columns,
        start=start,
        end=end,
        time_column=time_column,
        entity_column=entity_column,
        entity_value=entity_value,
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=descending,
    )
    result = query_parquet(query_request, db_root=settings.db_root)
    matched_rows = count_parquet_rows(query_request, db_root=settings.db_root, metadata=result.metadata)
    labels = page_labels(settings.db_root, scope, path, result.frame)
    return _query_json_response(result, matched_rows=matched_rows, labels=labels)


@router.get("/{scope}/arrow/{path:path}")
def query_dataset_arrow(
    request: Request,
    scope: DatasetScope,
    path: str,
    columns: str | None = Query(None, description="Comma-separated columns to project"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    time_column: str = Query("timestamp"),
    entity_column: str | None = Query(None),
    entity_value: list[str] | None = Query(None),
    limit: int | None = Query(100_000, ge=0, le=500_000),
    offset: int = Query(0, ge=0),
    order_by: str | None = Query(None),
    descending: bool = Query(False),
) -> Response:
    """Run a bounded query and return Arrow IPC bytes."""
    _reject_removed_backend_param(request)
    query_request = _build_query(
        scope=scope,
        path=path,
        columns=columns,
        start=start,
        end=end,
        time_column=time_column,
        entity_column=entity_column,
        entity_value=entity_value,
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=descending,
    )
    result = query_parquet(query_request, db_root=settings.db_root)
    return Response(
        content=to_arrow_ipc_bytes(result.frame),
        media_type="application/vnd.apache.arrow.file",
        headers={
            "X-Query-Backend": result.backend,
            "X-Returned-Rows": str(result.returned_rows),
            "X-Total-Rows": str(result.metadata.total_rows),
        },
    )


@router.get("/{scope}/stats/{path:path}")
def dataset_numeric_stats(
    request: Request,
    scope: DatasetScope,
    path: str,
    columns: str | None = Query(None, description="Comma-separated numeric columns"),
) -> Response:
    """Return numeric summary statistics for selected columns."""
    _reject_removed_backend_param(request)
    result = numeric_stats(
        scope=scope,
        path=path,
        columns=_parse_columns(columns),
        db_root=settings.db_root,
    )
    return _query_json_response(result)


def _build_query(
    *,
    scope: DatasetScope,
    path: str,
    columns: str | None,
    start: str | None,
    end: str | None,
    time_column: str,
    entity_column: str | None,
    entity_value: list[str] | None,
    limit: int | None,
    offset: int,
    order_by: str | None,
    descending: bool,
) -> ParquetQuery:
    return ParquetQuery(
        scope=scope,
        path=path,
        columns=_parse_columns(columns),
        start=start,
        end=end,
        time_column=time_column,
        entity_column=entity_column,
        entity_values=tuple(entity_value or ()),
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=descending,
    )


def _parse_columns(columns: str | None) -> tuple[str, ...] | None:
    if columns is None or not columns.strip():
        return None
    parsed = tuple(column.strip() for column in columns.split(",") if column.strip())
    return parsed or None


def _reject_removed_backend_param(request: Request) -> None:
    if "backend" in request.query_params:
        raise HTTPException(status_code=400, detail="data.query chooses the engine; backend is not a parameter")


def _query_json_response(
    result: QueryResult,
    *,
    matched_rows: int | None = None,
    labels: dict[str, dict[str, object]] | None = None,
) -> Response:
    return polars_json_response({
        "scope": result.metadata.scope,
        "path": result.metadata.path,
        "total_rows": result.metadata.total_rows,
        "matched_rows": result.metadata.total_rows if matched_rows is None else matched_rows,
        "returned_rows": result.returned_rows,
        "backend": result.backend,
        "data": result.frame,
        # Human labels for opaque ID columns on this page (db_api.entity_labels), when configured.
        **({"labels": labels} if labels else {}),
    })
