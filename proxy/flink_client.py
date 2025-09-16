from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from .config import Settings
from .schemas import SqlResponse

logger = logging.getLogger(__name__)


@dataclass
class FlinkJob:
    job_id: str
    state: str
    name: Optional[str] = None

    def is_running(self) -> bool:
        return self.state.upper() in {"CREATED", "RUNNING", "RECONCILING", "INITIALIZING"}


class FlinkProxyError(Exception):
    """Base class for failures interacting with the Flink REST API."""


class FlinkJobNotAvailableError(FlinkProxyError):
    """Raised when no suitable application job is available."""


class FlinkSubmissionError(FlinkProxyError):
    def __init__(self, message: str, status_code: int, body: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body

    def as_payload(self, truncate_bytes: int) -> Dict[str, str]:
        stderr = self.body
        if len(stderr) > truncate_bytes:
            stderr = stderr[:truncate_bytes] + "..."
        payload = {"error": self.message, "stderr": stderr}
        return payload


class FlinkApplicationClient:
    """Minimal client that routes SQL statements to a long running Flink application job."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._statement_client: Optional[httpx.AsyncClient] = None
        self._job_cache: Optional[FlinkJob] = None
        self._jar_id: Optional[str] = None
        self._lock = asyncio.Lock()

    async def submit_sql(self, sql: str, variables: Dict[str, str]) -> SqlResponse:
        job = await self.ensure_application_job()
        response = await self._dispatch_sql(job, sql, variables)
        if not response.job_id:
            response.job_id = job.job_id
        if not response.logs_url:
            response.logs_url = self._build_logs_url(job.job_id)
        return response

    async def ensure_application_job(self) -> FlinkJob:
        async with self._lock:
            if self._job_cache and self._job_cache.is_running():
                return self._job_cache

            job = await self._find_running_job()
            if job:
                self._job_cache = job
                return job

            job = await self._maybe_launch_job()
            if job:
                self._job_cache = job
                return job

            raise FlinkJobNotAvailableError(
                "No running Flink application job found. Configure FLINK_APPLICATION_JOB_ID or provide a launchable JAR."
            )

    async def _find_running_job(self) -> Optional[FlinkJob]:
        # Prefer explicit job ID when provided to avoid scanning
        if self._settings.flink_application_job_id:
            job = await self._get_job(self._settings.flink_application_job_id)
            if job and job.is_running():
                return job
            return None

        overview = await self._client.get("/jobs/overview")
        overview.raise_for_status()
        data = overview.json()
        jobs = data.get("jobs", [])
        for job_entry in jobs:
            state = job_entry.get("state", "")
            job_name = job_entry.get("name")
            job_id = job_entry.get("jid") or job_entry.get("jobid")
            if not job_id:
                continue
            if job_name and job_name != self._settings.flink_application_name:
                continue
            job = FlinkJob(job_id=job_id, state=state, name=job_name)
            if job.is_running():
                return job
        return None

    async def _get_job(self, job_id: str) -> Optional[FlinkJob]:
        response = await self._client.get(f"/jobs/{job_id}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        response.raise_for_status()
        payload = response.json()
        name = payload.get("name") or self._settings.flink_application_name
        state = payload.get("state", "UNKNOWN")
        return FlinkJob(job_id=job_id, state=state, name=name)

    async def _maybe_launch_job(self) -> Optional[FlinkJob]:
        jar_path = self._settings.flink_application_jar_path
        if not jar_path:
            return None
        jar_id = await self._ensure_jar_uploaded(jar_path)
        params = {"mode": "application"}
        payload: Dict[str, Any] = {}
        if self._settings.flink_application_entry_class:
            payload["entryClass"] = self._settings.flink_application_entry_class
        if self._settings.flink_application_program_args:
            payload["programArgsList"] = self._settings.flink_application_program_args
        response = await self._client.post(f"/jars/{jar_id}/run", params=params, json=payload)
        response.raise_for_status()
        data = response.json()
        job_id = data.get("jobid") or data.get("job_id")
        if not job_id:
            raise FlinkSubmissionError("Flink did not return a job id when launching the application", response.status_code, json.dumps(data))
        logger.info("Launched Flink application job %s", job_id)
        return FlinkJob(job_id=job_id, state="RUNNING", name=self._settings.flink_application_name)

    async def _ensure_jar_uploaded(self, jar_path: Path) -> str:
        if self._jar_id:
            return self._jar_id
        if not jar_path.exists():
            raise FlinkSubmissionError(
                f"Application JAR '{jar_path}' is not accessible inside the proxy container",
                status_code=400,
                body="",
            )
        jar_bytes = jar_path.read_bytes()
        files = {"jarfile": (jar_path.name, jar_bytes, "application/java-archive")}
        response = await self._client.post("/jars/upload", files=files)
        response.raise_for_status()
        data = response.json()
        filename = data.get("filename")
        if not filename:
            raise FlinkSubmissionError("Unable to determine uploaded JAR identifier", response.status_code, json.dumps(data))
        jar_id = Path(filename).name
        self._jar_id = jar_id
        logger.info("Uploaded application jar %s", jar_id)
        return jar_id

    async def _dispatch_sql(self, job: FlinkJob, sql: str, variables: Dict[str, str]) -> SqlResponse:
        endpoint = self._settings.flink_statement_endpoint
        payload = {"sql": sql, "vars": variables, "job_id": job.job_id}
        if endpoint:
            url = endpoint.format(job_id=job.job_id)
            client = await self._get_statement_client(url)
            if client is self._client and not url.startswith("/"):
                url = "/" + url
            response = await client.post(url, json=payload)
        else:
            response = await self._client.post(f"/jobs/{job.job_id}/control/submit-sql", json=payload)
        if response.status_code >= 400:
            text = response.text or ""
            raise FlinkSubmissionError(
                f"Flink REST API returned {response.status_code} when submitting SQL", response.status_code, text
            )
        if response.status_code == httpx.codes.NO_CONTENT:
            return SqlResponse(job_id=job.job_id, status="SUBMITTED", logs_url=self._build_logs_url(job.job_id))
        data = response.json() if response.content else {}
        status = data.get("status", "SUBMITTED")
        logs_url = data.get("logs_url")
        job_id = data.get("job_id") or job.job_id
        return SqlResponse(job_id=job_id, status=status, logs_url=logs_url)

    async def _get_statement_client(self, url: str) -> httpx.AsyncClient:
        if url.startswith("http://") or url.startswith("https://"):
            if self._statement_client is None or self._statement_client.is_closed:
                self._statement_client = httpx.AsyncClient(timeout=self._settings.http_timeout_seconds)
            return self._statement_client
        return self._client

    def _build_logs_url(self, job_id: str) -> Optional[str]:
        if self._settings.logs_base_url:
            return urljoin(str(self._settings.logs_base_url), job_id)
        base = str(self._settings.flink_rest_url).rstrip("/")
        return f"{base}/#/job/{job_id}"

    async def close(self) -> None:
        if self._statement_client and not self._statement_client.is_closed:
            await self._statement_client.aclose()
