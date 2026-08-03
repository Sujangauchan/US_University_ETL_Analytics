select
    hash(subject_code) as subject_key,
    subject_code,
    subject_title,
    credit_points,
    current_timestamp as _loaded_at
from {{ref('stg_subjects')}}
