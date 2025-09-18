from __future__ import annotations

import logging
import secrets
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from .config import Settings, get_settings
from .flink_client import FlinkApplicationClient, FlinkJobNotAvailableError, FlinkSubmissionError
from .idempotency import IdempotencyCache
from .schemas import ErrorResponse, SqlRequest, SqlResponse

logger = logging.getLogger(__name__)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    app = FastAPI(title="Flink SQL Proxy", version="0.1.0")
    cache = IdempotencyCache[SqlResponse](settings.idempotency_ttl_seconds)

    app.state.settings = settings
    app.state.idempotency_cache = cache
    app.dependency_overrides[get_settings] = lambda: settings

    @app.on_event("startup")
    async def _startup() -> None:
        logger.info("Starting Flink SQL proxy targeting %s", settings.flink_rest_url)
        timeout = httpx.Timeout(settings.http_timeout_seconds)
        app.state.http_client = httpx.AsyncClient(base_url=str(settings.flink_rest_url), timeout=timeout)
        app.state.flink_client = FlinkApplicationClient(settings, app.state.http_client)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        logger.info("Shutting down Flink SQL proxy")
        flink_client: FlinkApplicationClient = app.state.flink_client
        await flink_client.close()
        await app.state.http_client.aclose()

    @app.get("/healthz", response_model=dict)
    async def healthcheck() -> dict:
        return {"status": "ok"}

    @app.post("/v1/sql", response_model=SqlResponse, responses={502: {"model": ErrorResponse}})
    async def submit_sql(
        payload: SqlRequest,
        request: Request,
        settings: Settings = Depends(get_settings),
        authorization: Optional[str] = Header(default=None),
        idempotency_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> SqlResponse:
        _authenticate(settings, authorization)
        cache: IdempotencyCache[SqlResponse] = request.app.state.idempotency_cache
        key = idempotency_header or payload.idempotency_key
        if key:
            cached = await cache.get(key)
            if cached:
                logger.debug("Returning cached result for idempotency key %s", key)
                return cached
        try:
            flink_client: FlinkApplicationClient = request.app.state.flink_client
        except AttributeError as exc:  # pragma: no cover - should not happen after startup
            logger.exception("Flink client not initialised")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Proxy not initialised") from exc
        try:
            response = await flink_client.submit_sql(payload.sql, payload.variables)
        except FlinkJobNotAvailableError as exc:
            logger.warning("Unable to locate running Flink application job: %s", exc)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        except FlinkSubmissionError as exc:
            logger.error("Flink submission failed: %s", exc)
            detail = exc.as_payload(settings.stderr_truncate_bytes)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
        except httpx.HTTPError as exc:
            logger.error("HTTP error while communicating with Flink: %s", exc)
            detail = {"error": "Flink REST API request failed", "stderr": str(exc)}
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
        if key:
            await cache.set(key, response)
        return response

    return app


def _authenticate(settings: Settings, authorization: Optional[str]) -> None:
    expected = settings.auth_token
    if not expected:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    provided = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(expected, provided):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")


app = create_app()
