{% snapshot dim_program_snapshot %}

{{
    config(
      target_schema='warehouse',
      strategy='check',
      unique_key='program_id',
      check_cols=['program_name', 'department', 'degree_level', 'total_credit_points_required']
    )
}}

-- Main Query

select
    program_id,                            
    program_name,
    department,
    degree_level,
    total_credit_points_required,
    current_timestamp as _loaded_at
from {{ ref('stg_programs') }}

{% endsnapshot %}