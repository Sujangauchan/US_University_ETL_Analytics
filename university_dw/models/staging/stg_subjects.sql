select
    subject_code,
    subject_title,
    credit_points,
    _ingested_at
from {{ source('raw_landed', 'raw_subjects') }}