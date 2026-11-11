"""FRED client secret-resolution tests.

USAGE::

    uv run pytest packages/platform/clients/fred-client/tests -q
"""

from __future__ import annotations

import traceback

import httpx
import pytest
from fred_client import FredClient

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_default_client_resolves_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "fake-env-key")

    with FredClient() as client:
        assert client.api_key == "fake-env-key"


def test_explicit_key_bypasses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with FredClient(api_key="test-key") as client:
        assert client.api_key == "test-key"


def test_missing_environment_key_fails_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with FredClient() as client, pytest.raises(ValueError, match="FRED_API_KEY is required"):
        _ = client.api_key


def test_public_observations_do_not_require_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    def respond(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {
            "id": "DGS10",
            "cosd": "2026-08-01",
            "coed": "2026-09-01",
        }
        return httpx.Response(
            200,
            text="observation_date,DGS10\n2026-08-29,.\n2026-09-01,4.23\n",
        )

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as http_client:
        with FredClient(client=http_client) as client:
            payload = client.get_series_observations_public(
                "DGS10",
                observation_start="2026-08-01",
                observation_end="2026-09-01",
            )

    assert payload == {
        "observations": [
            {"date": "2026-08-29", "value": "."},
            {"date": "2026-09-01", "value": "4.23"},
        ]
    }


def test_public_observations_send_library_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare product UA is tarpitted by fred.stlouisfed.org; pin the request shape that is served."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="observation_date,DTB3\n1985-01-02,7.80\n")

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport, headers={"User-Agent": "quant-factory/0.1"}) as http_client:
        with FredClient(client=http_client) as client:
            payload = client.get_series_observations_public("DTB3", observation_start="1985-01-01")

    (request,) = seen
    assert request.method == "GET"
    assert f"{request.url.scheme}://{request.url.host}{request.url.path}" == FredClient._PUBLIC_CSV_URL
    assert dict(request.url.params) == {"id": "DTB3", "cosd": "1985-01-01"}
    assert request.headers["User-Agent"] == f"quant-factory/0.1 python-httpx/{httpx.__version__}"
    assert "api_key" not in request.url.params
    assert payload == {"observations": [{"date": "1985-01-02", "value": "7.80"}]}


def test_http_errors_do_not_expose_api_key() -> None:
    secret = "never-print-this"

    def fail(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(fail)
    with httpx.Client(base_url="https://example.test", transport=transport) as http_client:
        with FredClient(api_key=secret, client=http_client) as client:
            with pytest.raises(RuntimeError) as caught:
                client.get_series("GDP")

    rendered = "".join(traceback.format_exception(caught.value))
    assert secret not in rendered
    assert caught.value.__cause__ is None


def test_release_dates_and_first_release_params() -> None:
    seen: list[dict[str, str]] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append({**dict(request.url.params), "path": request.url.path})
        return httpx.Response(200, json={"release_dates": []})

    transport = httpx.MockTransport(record)
    with httpx.Client(base_url="https://example.test", transport=transport) as http_client:
        with FredClient(api_key="k", client=http_client) as client:
            client.get_release_dates(10, realtime_start="1776-07-04", include_release_dates_with_no_data=True)
            client.get_series_observations("CPIAUCSL", output_type=4)

    assert seen[0]["path"] == "/fred/release/dates"
    assert (seen[0]["release_id"], seen[0]["include_release_dates_with_no_data"]) == ("10", "true")
    assert seen[1]["output_type"] == "4"
