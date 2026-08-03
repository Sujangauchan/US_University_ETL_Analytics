select
    result_id,
    subject_enrollment_id,
    assessment_id,
    raw_score,
    submitted_at,
    updated_at,
    _ingested_at
from {{ source('raw_landed', 'raw_assessment_results') }}