from __future__ import annotations

import sys
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
import respx
from dbt.contracts.connection import Connection, ConnectionState

# Ensure the adapter package is importable when running tests from repository root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dbt_flink_http_adapter.connections import FlinkHttpConnectionManager, FlinkHttpCredentials  # noqa: E402


class TestConnectionManager(FlinkHttpConnectionManager):
    @contextmanager
    def exception_handler(self, sql: str):  # type: ignore[override]
        yield

    def cancel(self, connection: Connection) -> None:  # type: ignore[override]
        return


@pytest.fixture
def manager() -> FlinkHttpConnectionManager:
    profile = SimpleNamespace()
    return TestConnectionManager(profile)


@respx.mock
def test_add_query_posts_to_proxy(manager: FlinkHttpConnectionManager) -> None:
    credentials = FlinkHttpCredentials(host="http://proxy:8080")
    connection = Connection(
        type="flink_http",
        name="test",
        state=ConnectionState.INIT,
        handle=None,
        credentials=credentials,
    )
    manager.set_thread_connection(connection)
    manager.open(connection)
    respx.post("http://proxy:8080/v1/sql").mock(
        return_value=httpx.Response(200, json={"job_id": "job-1", "status": "RUNNING"})
    )
    _, cursor = manager.add_query("SELECT 1", auto_begin=False)
    response = manager.get_response(cursor)
    assert response.code == "RUNNING"
    assert "job-1" in str(response)
    assert respx.calls.call_count == 1
