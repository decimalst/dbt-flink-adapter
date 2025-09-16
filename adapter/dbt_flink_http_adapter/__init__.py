from __future__ import annotations

from pathlib import Path

from dbt.adapters.base import AdapterPlugin

from .connections import FlinkHttpConnectionManager, FlinkHttpCredentials
from .impl import FlinkHttpAdapter


def get_include_path() -> Path:
    return Path(__file__).parent / "include" / "flink_http"


Plugin = AdapterPlugin(
    adapter=FlinkHttpAdapter,
    credentials=FlinkHttpCredentials,
    include_path=str(get_include_path()),
)

__all__ = ["Plugin", "FlinkHttpAdapter", "FlinkHttpConnectionManager", "FlinkHttpCredentials"]
