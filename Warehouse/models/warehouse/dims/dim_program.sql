select
    hash(program_id) as program_key, 
    program_id,
    program_name,
    department,
    degree_level,
    total_credit_points_required,
    dbt_valid_from as effective_from,  
    _loaded_at
from {{ ref('dim_program_snapshot') }}
where dbt_valid_to is null