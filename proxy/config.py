from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the SQL proxy."""

    flink_rest_url: AnyHttpUrl = Field(
        "http://jobmanager:8081", env="FLINK_REST_URL", description="Base REST endpoint for the Flink cluster"
    )
    flink_application_name: str = Field(
        "sql-runner",
        env="FLINK_APPLICATION_NAME",
        description="Human friendly name for the long running application job used to execute SQL statements.",
    )
    flink_application_job_id: Optional[str] = Field(
        None,
        env="FLINK_APPLICATION_JOB_ID",
        description="Explicit job identifier to reuse when routing SQL to a long running application job.",
    )
    flink_application_jar_path: Optional[Path] = Field(
        None,
        env="FLINK_APPLICATION_JAR_PATH",
        description="Local path to an application JAR that should be uploaded if the target job is not yet running.",
    )
    flink_application_entry_class: Optional[str] = Field(
        None,
        env="FLINK_APPLICATION_ENTRY_CLASS",
        description="Fully qualified entry class for launching the long running application job in Flink.",
    )
    flink_application_program_args: List[str] = Field(
        default_factory=list,
        env="FLINK_APPLICATION_PROGRAM_ARGS",
        description="Additional program arguments to forward when launching the application job.",
    )
    flink_statement_endpoint: Optional[str] = Field(
        None,
        env="FLINK_STATEMENT_ENDPOINT",
        description=(
            "Optional relative or absolute URL exposed by the long running application job that accepts SQL payloads. "
            "If not provided, the proxy will attempt to post to /jobs/{job_id}/control/submit-sql on the Flink REST API."
        ),
    )
    auth_token: Optional[str] = Field(
        None,
        env="AUTH_TOKEN",
        description="Optional bearer token expected in Authorization headers. If set, requests must provide a matching token.",
    )
    logs_base_url: Optional[AnyHttpUrl] = Field(
        None,
        env="FLINK_LOGS_BASE_URL",
        description="Base URL for constructing links to Flink job logs in responses.",
    )
    http_timeout_seconds: float = Field(10.0, env="HTTP_TIMEOUT_SECONDS", ge=1.0, le=120.0)
    idempotency_ttl_seconds: int = Field(600, env="IDEMPOTENCY_TTL_SECONDS", ge=1, le=3600)
    stderr_truncate_bytes: int = Field(2048, env="STDERR_TRUNCATE_BYTES", ge=256, le=16384)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @field_validator("flink_application_program_args", mode="before")
    @classmethod
    def _split_program_args(cls, value):
        if isinstance(value, str):
            return [item for item in value.split() if item]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
