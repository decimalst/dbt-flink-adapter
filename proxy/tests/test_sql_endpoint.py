from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import respx
from asgi_lifespan import LifespanManager

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from proxy.config import Settings
from proxy.main import create_app


@pytest_asyncio.fixture
async def app() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(
        flink_rest_url="http://flink:8081",
        auth_token="secret",
        logs_base_url="http://jobmanager:8081/#/job/",
    )
    fastapi_app = create_app(settings)
    async with LifespanManager(fastapi_app):
        async with httpx.AsyncClient(app=fastapi_app, base_url="http://test") as client:
            yield client


@pytest.fixture
def respx_routes() -> respx.MockRouter:
    with respx.mock(base_url="http://flink:8081", assert_all_called=False) as router:
        yield router


@pytest.mark.asyncio
async def test_submit_sql_success(app: httpx.AsyncClient, respx_routes: respx.MockRouter) -> None:
    respx_routes.get("/jobs/overview").mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"jid": "abc123", "state": "RUNNING", "name": "sql-runner"}]},
        )
    )
    respx_routes.post("/jobs/abc123/control/submit-sql").mock(
        return_value=httpx.Response(
            200,
            json={"job_id": "abc123", "status": "ACCEPTED", "logs_url": "http://jm/jobs/abc123"},
        )
    )
    response = await app.post(
        "/v1/sql",
        headers={"Authorization": "Bearer secret", "Idempotency-Key": "demo"},
        json={"sql": "SELECT 1", "vars": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "abc123"
    assert body["status"] == "ACCEPTED"
    assert body["logs_url"].endswith("abc123")


@pytest.mark.asyncio
async def test_authentication_required(app: httpx.AsyncClient) -> None:
    response = await app.post("/v1/sql", json={"sql": "SELECT 1"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_idempotency_returns_cached_result(app: httpx.AsyncClient, respx_routes: respx.MockRouter) -> None:
    respx_routes.get("/jobs/overview").mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"jid": "xyz", "state": "RUNNING", "name": "sql-runner"}]},
        )
    )
    respx_routes.post("/jobs/xyz/control/submit-sql").mock(
        side_effect=[
            httpx.Response(200, json={"job_id": "xyz", "status": "RUNNING"}),
            httpx.Response(200, json={"job_id": "xyz", "status": "RUNNING"}),
        ]
    )
    headers = {"Authorization": "Bearer secret", "Idempotency-Key": "abc"}
    payload = {"sql": "SELECT 1", "vars": {}}
    first = await app.post("/v1/sql", headers=headers, json=payload)
    second = await app.post("/v1/sql", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert respx_routes.calls.call_count == 2  # overview + first execution, second hits cache
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_flink_error_maps_to_502(app: httpx.AsyncClient, respx_routes: respx.MockRouter) -> None:
    respx_routes.get("/jobs/overview").mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"jid": "xyz", "state": "RUNNING", "name": "sql-runner"}]},
        )
    )
    respx_routes.post("/jobs/xyz/control/submit-sql").mock(
        return_value=httpx.Response(500, text="boom"),
    )
    response = await app.post(
        "/v1/sql",
        headers={"Authorization": "Bearer secret"},
        json={"sql": "SELECT 1"},
    )
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["stderr"].startswith("boom")


@pytest.mark.asyncio
async def test_empty_sql_rejected(app: httpx.AsyncClient) -> None:
    response = await app.post(
        "/v1/sql",
        headers={"Authorization": "Bearer secret"},
        json={"sql": "   "},
    )
    assert response.status_code == 422
