select
    assessment_id,
    offering_id,
    title,
    weight_percentage,
    max_score,
    _ingested_at
from {{ source('raw_landed', 'raw_assessments') }}