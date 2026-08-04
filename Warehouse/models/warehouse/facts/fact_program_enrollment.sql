-- fact_program_enrollment.sql
{{
    config(
        materialized='incremental',
        unique_key='program_enrollment_key',
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

/*
    Grain: 1 row per program_enrollment_id (latest known version)
    Raw lake is append-only per enrollment -> dedup to latest by _ingested_at before loading
*/

with source as (
    select *
    from {{ ref('stg_program_enrollments') }}
    {% if is_incremental() %}
    where _ingested_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

deduped as (
    select *,
        row_number() over (partition by program_enrollment_id order by _ingested_at desc) as rn
    from source
)

select
    hash(d.program_enrollment_id) as program_enrollment_key,
    d.program_enrollment_id as program_enrollment_id,
    ds.student_key as student_key,
    dp.program_key as program_key,
    d.enrollment_date as enrollment_date,
    d.completion_date as completion_date,
    d.status as status,
    d.final_degree_result as final_degree_result,
    current_timestamp as _loaded_at
from deduped d
left join {{ ref('dim_student') }} ds on d.student_id = ds.student_id
left join {{ ref('dim_program') }} dp on d.program_id = dp.program_id
where d.rn = 1