{% materialization table, adapter='flink_http' %}
  {%- set sql = get_create_table_as_sql(False, this, compiled_sql) -%}
  {% call statement('main', fetch_result=False) %}
    {{ sql }}
  {% endcall %}
  {{ return({'relations': [this]}) }}
{% endmaterialization %}
