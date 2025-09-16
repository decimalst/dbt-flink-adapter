# dbt-flink-http-adapter (hackathon edition)

This minimal adapter wraps the FastAPI proxy exposed in `proxy/` so that dbt can issue
compiled SQL statements to a Flink cluster over HTTP. It intentionally omits catalog
inspection and most advanced adapter features – the goal is to demonstrate the plumbing
required for `dbt run` against a long running Flink application job managed by the proxy.

## Installation

```bash
pip install -e adapter/
```

## Profiles.yml snippet

```yaml
project:
  target: dev
  outputs:
    dev:
      type: flink_http
      host: http://flink-sql-proxy:8080
      token: ${AUTH_TOKEN}
      schema: default_database
      database: default_catalog
```

See `examples/dbt_http_demo` for a tiny dbt project wired to the adapter.
