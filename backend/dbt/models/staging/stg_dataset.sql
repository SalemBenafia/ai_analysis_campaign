{{ config(materialized='external', location=var('target_path'), format='parquet') }}

{#-
  Generic staging model, parameterized per dataset:
    source_path : s3:// path of the processed parquet (original column names)
    target_path : s3:// path of the marts parquet (semantic snake_case names)
    column_map  : { "Original Name": "semantic_name", ... }
  Renames columns to semantic names and deduplicates full rows.
-#}

{% set cols = var('column_map') %}

select distinct
{% for orig, sem in cols.items() %}
    "{{ orig }}" as "{{ sem }}"{{ "," if not loop.last }}
{% endfor %}
from read_parquet('{{ var("source_path") }}')
