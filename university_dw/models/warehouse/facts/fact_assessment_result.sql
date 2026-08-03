-- fact_assessment_result.sql
{{
    config(
        materialized='incremental',
        unique_key='result_key',
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

/*
    Grain: 1 row per result_id (latest known version)
    Raw lake is append-only per result -> dedup to latest by _ingested_at before loading
*/

with source as (
    select *
    from {{ ref('stg_assessment_results') }}
    {% if is_incremental() %}
    where _ingested_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

deduped as (
    select *,
        row_number() over (partition by result_id order by _ingested_at desc) as rn
    from source
)

select
    hash(d.result_id) as result_key,
    d.result_id as result_id,
    se.subject_enrollment_key,
    se.subject_key as subject_key,
    se.student_key as student_key,
    se.program_key as program_key,
    a.assessment_key,
    d.raw_score as raw_score,
    d.submitted_at as submitted_at,
    current_timestamp as _loaded_at
from deduped d
left join {{ ref('fact_subject_enrollment') }} se
    on d.subject_enrollment_id = se.subject_enrollment_id
left join {{ ref('dim_assessment') }} a
    on d.assessment_id = a.assessment_id
where d.rn = 1