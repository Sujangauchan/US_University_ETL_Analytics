select
    program_enrollment_id,
    student_id,
    program_id,
    enrollment_date,
    completion_date,
    status,
    final_degree_result,
    updated_at,
    _ingested_at
from {{ source('raw_landed', 'raw_program_enrollments') }}