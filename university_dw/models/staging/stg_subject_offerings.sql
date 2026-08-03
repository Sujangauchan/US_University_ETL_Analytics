select
    offering_id,
    subject_code,
    semester_id,
    coordinator_name,
    _ingested_at
from {{ source('raw_landed', 'raw_subject_offerings') }}