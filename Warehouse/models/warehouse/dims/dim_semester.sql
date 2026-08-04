select
    hash(semester_id) as semester_key,
    semester_id,
    semester_name,
    academic_year,
    start_date,
    end_date,
    current_timestamp as _loaded_at
from {{ref('stg_semesters')}}
