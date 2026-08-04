select
    hash(so.offering_id) as offering_key,
    so.offering_id as offering_id,
    ds.subject_key as subject_key,
    dsem.semester_key as semester_key,
    so.coordinator_name as coordinator_name,
    current_timestamp as _loaded_at
from {{ ref('stg_subject_offerings') }} so
left join {{ ref('dim_subject') }} ds on so.subject_code = ds.subject_code
left join {{ ref('dim_semester') }} dsem on so.semester_id = dsem.semester_id