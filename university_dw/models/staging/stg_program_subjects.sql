select
    program_subject_id,
    program_id,
    subject_code,
    subject_type,
    recommended_semester,
    _ingested_at
from {{ source('raw_landed', 'raw_program_subjects') }}