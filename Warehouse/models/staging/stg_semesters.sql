select
    semester_id,
    semester_name,
    academic_year,
    start_date,
    end_date,
    _ingested_at
from {{ source('raw_landed', 'raw_semesters') }}