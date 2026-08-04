select
    program_id,
    program_name,
    department,
    degree_level,
    total_credit_points_required,
    _ingested_at
from {{ source('raw_landed', 'raw_programs') }}