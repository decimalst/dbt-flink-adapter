from __future__ import annotations

import agate
from dbt.adapters.base import BaseRelation
from dbt.adapters.sql.impl import SQLAdapter

from .connections import FlinkHttpConnectionManager


class FlinkHttpAdapter(SQLAdapter):
    """Minimal dbt adapter that proxies SQL execution to the HTTP service."""

    ConnectionManager = FlinkHttpConnectionManager
    Relation = BaseRelation

    @classmethod
    def date_function(cls) -> str:
        return "CURRENT_DATE"

    @classmethod
    def convert_text_type(cls, agate_table: agate.Table, col_idx: int) -> str:  # pragma: no cover - defaults unused
        return "STRING"

    @classmethod
    def convert_number_type(cls, agate_table: agate.Table, col_idx: int) -> str:
        return "DECIMAL"

    @classmethod
    def convert_boolean_type(cls, agate_table: agate.Table, col_idx: int) -> str:
        return "BOOLEAN"

    @classmethod
    def convert_datetime_type(cls, agate_table: agate.Table, col_idx: int) -> str:
        return "TIMESTAMP"

    @classmethod
    def convert_date_type(cls, agate_table: agate.Table, col_idx: int) -> str:
        return "DATE"

    @classmethod
    def convert_time_type(cls, agate_table: agate.Table, col_idx: int) -> str:
        return "TIME"

    @classmethod
    def is_cancelable(cls) -> bool:
        return False
