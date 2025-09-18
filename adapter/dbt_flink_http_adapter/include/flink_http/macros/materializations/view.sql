{% materialization view, adapter='flink_http' %}
  {%- set sql = get_create_view_sql(this, compiled_sql, or_replace=True) -%}
  {% call statement('main', fetch_result=False) %}
    {{ sql }}
  {% endcall %}
  {{ return({'relations': [this]}) }}
{% endmaterialization %}
