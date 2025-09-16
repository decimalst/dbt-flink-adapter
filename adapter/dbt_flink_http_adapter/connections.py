from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from dbt.adapters.sql.connections import SQLConnectionManager
from dbt.contracts.connection import AdapterResponse, Connection, ConnectionState, Credentials
from dbt.events.functions import fire_event
from dbt.events.types import SQLQueryStatus
from dbt.exceptions import DbtDatabaseError


@dataclass
class FlinkHttpCredentials(Credentials):
    host: str = ""
    token: Optional[str] = None
    database: str = "default_catalog"
    schema: str = "default_database"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.host:
            raise DbtDatabaseError("Flink HTTP credentials require a host URL")

    @property
    def type(self) -> str:  # type: ignore[override]
        return "flink_http"

    @property
    def unique_field(self) -> str:  # type: ignore[override]
        return self.host

    def _connection_keys(self) -> tuple[str, ...]:
        return ("host", "schema", "database", "timeout_seconds")


@dataclass
class FlinkHttpResult:
    job_id: Optional[str]
    status: str
    logs_url: Optional[str] = None


class FlinkHttpCursor:
    def __init__(self, client: httpx.Client, credentials: FlinkHttpCredentials) -> None:
        self._client = client
        self._credentials = credentials
        self._last_result: Optional[FlinkHttpResult] = None

    def execute(self, sql: str, bindings: Optional[Any] = None) -> None:  # noqa: ARG002
        if not sql or not sql.strip():
            raise DbtDatabaseError("Flink HTTP adapter received an empty SQL payload")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        }
        if self._credentials.token:
            headers["Authorization"] = f"Bearer {self._credentials.token}"
        payload = {"sql": sql}
        response = self._client.post("/v1/sql", headers=headers, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - exercised via adapter tests
            message = response.text or exc.args[0]
            raise DbtDatabaseError(f"Flink SQL proxy returned {response.status_code}: {message}") from exc
        data: dict[str, Any] = {}
        if response.content:
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = {}
        result = FlinkHttpResult(
            job_id=data.get("job_id"),
            status=data.get("status", "SUBMITTED"),
            logs_url=data.get("logs_url"),
        )
        self._last_result = result

    def fetchone(self) -> None:  # pragma: no cover - the adapter never fetches results
        return None

    def fetchall(self) -> list[Any]:  # pragma: no cover
        return []

    @property
    def response(self) -> Optional[FlinkHttpResult]:
        return self._last_result


class FlinkHttpConnection:
    def __init__(self, credentials: FlinkHttpCredentials) -> None:
        timeout = httpx.Timeout(credentials.timeout_seconds)
        self._client = httpx.Client(base_url=credentials.host, timeout=timeout)
        self._credentials = credentials

    def cursor(self) -> FlinkHttpCursor:
        return FlinkHttpCursor(self._client, self._credentials)

    def close(self) -> None:
        self._client.close()


class FlinkHttpConnectionManager(SQLConnectionManager):
    TYPE = "flink_http"

    @classmethod
    def open(cls, connection: Connection) -> Connection:
        if connection.state == ConnectionState.OPEN:
            return connection
        credentials = connection.credentials
        if not isinstance(credentials, FlinkHttpCredentials):
            raise DbtDatabaseError("Invalid credentials type for Flink HTTP adapter")
        connection.handle = FlinkHttpConnection(credentials)
        connection.state = ConnectionState.OPEN
        connection.transaction_open = False
        return connection

    @classmethod
    def close(cls, connection: Connection) -> Connection:
        handle = connection.handle
        if handle is not None:
            handle.close()
        connection.handle = None
        connection.state = ConnectionState.CLOSED
        connection.transaction_open = False
        return connection

    @classmethod
    def cancel_open(cls, connection: Connection) -> None:  # pragma: no cover - not used
        handle = connection.handle
        if handle is not None:
            handle.close()
        connection.handle = None
        connection.state = ConnectionState.CLOSED

    @classmethod
    def get_response(cls, cursor: FlinkHttpCursor) -> AdapterResponse:
        result = cursor.response or FlinkHttpResult(job_id=None, status="SUBMITTED")
        message = result.status
        if result.job_id:
            message = f"Job {result.job_id} status={result.status}"
        response = AdapterResponse(_message=message, code=result.status, rows_affected=None)
        fire_event(
            SQLQueryStatus(status=message, elapsed=0.0, node_info=None),
        )
        return response

    @classmethod
    def add_begin_query(cls) -> str:
        return ""

    @classmethod
    def add_commit_query(cls) -> str:
        return ""

    def begin(self) -> None:
        connection = self.get_thread_connection()
        connection.transaction_open = False

    def commit(self) -> None:
        connection = self.get_thread_connection()
        connection.transaction_open = False
