# Re-export the AdapterPlugin instance expected by dbt-core<=1.5 as Plugin
from dbt_flink_http_adapter import Plugin  # variable defined in impl package
from .__version__ import version  # optional: expose version for inspection

__all__ = ["Plugin", "version"]
