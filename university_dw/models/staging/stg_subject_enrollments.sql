select
    subject_enrollment_id,
    program_enrollment_id,
    offering_id,
    status,
    final_mark,
    final_grade,
    updated_at,
    _ingested_at
from {{ source('raw_landed', 'raw_subject_enrollments') }}