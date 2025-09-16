{{ config(materialized='table') }}

with source_data as (
    select 1 as id, 'hello from dbt over HTTP' as message
)

select * from source_data
