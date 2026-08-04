-- fact_subject_enrollment.sql
{{
    config(
        materialized='incremental',
        unique_key='subject_enrollment_key',
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

/*
    Grain: 1 row per subject_enrollment_id (latest known version)
    Raw lake is append-only per enrollment -> dedup to latest by _ingested_at before loading
*/

with source as (
    select *
    from {{ ref('stg_subject_enrollments') }}
    {% if is_incremental() %}
    where _ingested_at > (select max(_loaded_at) from {{ this }})
    {% endif %}
),

deduped as (
    select *,
        row_number() over (partition by subject_enrollment_id order by _ingested_at desc) as rn
    from source
)

select
    hash(d.subject_enrollment_id) as subject_enrollment_key,
    d.subject_enrollment_id as subject_enrollment_id,
    so.subject_key as subject_key,
    pe.program_enrollment_key,
    pe.student_key as student_key,
    pe.program_key as program_key,
    so.offering_key,
    d.status as status,
    d.final_mark as final_mark,
    d.final_grade as final_grade,
    current_timestamp as _loaded_at
from deduped d
left join {{ ref('fact_program_enrollment') }} pe
    on d.program_enrollment_id = pe.program_enrollment_id
left join {{ ref('dim_subject_offering') }} so
    on d.offering_id = so.offering_id
where d.rn = 1