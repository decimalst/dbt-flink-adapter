from importlib.metadata import version as _ver, PackageNotFoundError

try:
    # must match [project].name in pyproject.toml
    version = _ver("dbt-flink-http-adapter")
except PackageNotFoundError:
    version = "0.0.0"
