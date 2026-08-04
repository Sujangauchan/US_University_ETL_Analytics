select
    student_id,
    first_name,
    last_name,
    email,
    created_at,
    _ingested_at
from {{ source('raw_landed', 'raw_students') }}