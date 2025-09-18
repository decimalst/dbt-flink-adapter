from __future__ import annotations

from typing import Dict, Optional

from pydantic import AnyHttpUrl, BaseModel, Field, constr


class SqlRequest(BaseModel):
    sql: constr(strip_whitespace=True, min_length=1)  # type: ignore[valid-type]
    variables: Dict[str, str] = Field(default_factory=dict, alias="vars")
    idempotency_key: Optional[str] = Field(None, alias="idempotency_key")

    class Config:
        allow_population_by_field_name = True
        anystr_strip_whitespace = True


class SqlResponse(BaseModel):
    job_id: str
    status: str
    logs_url: Optional[AnyHttpUrl] = None


class ErrorResponse(BaseModel):
    detail: str
    error: Optional[str] = None
    stderr: Optional[str] = None
