"""Encode provider query parameters and validate dynamic response essentials.

USAGE: from blockworks_client._wire import encode_query
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .exceptions import BlockworksConfigError, BlockworksDecodeError

# --------------------------------------------------------------------------- #
# Request encoding
# --------------------------------------------------------------------------- #


def safe_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise BlockworksConfigError("path must be an origin-relative Blockworks API path")
    if "\\" in path or any(ord(c) < 32 for c in path):
        raise BlockworksConfigError("path contains an invalid character")
    parts = urlsplit(path)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise BlockworksConfigError("path must not contain an origin, query, or fragment")
    decoded = unquote(path)
    if decoded.startswith("//") or any(segment in (".", "..") for segment in decoded.split("/")):
        raise BlockworksConfigError("path traversal is not allowed")
    return path


def path_value(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool) or str(value) == "":
        raise BlockworksConfigError("path identifiers must be nonempty strings or integers")
    return quote(str(value), safe="")


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise BlockworksConfigError("naive datetimes are not accepted")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int, float)):
        return str(value)
    raise BlockworksConfigError("unsupported query parameter value")


def encode_query(params: Mapping[str, object] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in (params or {}).items():
        if not isinstance(name, str) or not name or any(c in name for c in "\r\n&=?"):
            raise BlockworksConfigError("invalid query parameter name")
        if value is None:
            continue
        if isinstance(value, Mapping):
            raise BlockworksConfigError("nested query values are not supported")
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if not value:
                raise BlockworksConfigError(f"{name} cannot be empty")
            result[name] = ",".join(_scalar(item) for item in value)
        else:
            result[name] = _scalar(value)
    return result


# --------------------------------------------------------------------------- #
# Response checks
# --------------------------------------------------------------------------- #


def decode_json(content: bytes, family: str) -> dict[str, Any]:
    try:
        body = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise BlockworksDecodeError("Blockworks returned invalid JSON") from None
    if not isinstance(body, dict):
        raise BlockworksDecodeError("Blockworks response must be a JSON object")
    if family in ("data-api", "token-unlocks", "monitoring-watchlists", "charts", "monitoring") and "data" not in body:
        raise BlockworksDecodeError("Blockworks response is missing data")
    return body


def validate_timeseries(body: dict[str, Any], single: bool) -> None:
    data = body.get("data")
    if not isinstance(data, dict):
        raise BlockworksDecodeError("timeseries data must be an object")
    schema = data.get("point_schema")
    if (
        not isinstance(schema, list)
        or not schema
        or not all(isinstance(x, dict) and isinstance(x.get("field"), str) for x in schema)
    ):
        raise BlockworksDecodeError("timeseries point_schema is invalid")
    entries = [data] if single else data.get("series")
    if not isinstance(entries, list):
        raise BlockworksDecodeError("timeseries series must be an array")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("points"), list):
            raise BlockworksDecodeError("timeseries points must be an array")
        for point in entry["points"]:
            if not isinstance(point, list) or len(point) != len(schema):
                raise BlockworksDecodeError("timeseries point width differs from point_schema")
