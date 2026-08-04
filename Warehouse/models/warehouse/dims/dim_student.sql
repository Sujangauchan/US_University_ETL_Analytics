select
    hash(student_id) as student_key,
    student_id,
    first_name,
    last_name,
    email,
    created_at,
    current_timestamp as _loaded_at
from {{ref('stg_students')}}
