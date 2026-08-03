select
    hash(sa.assessment_id) as assessment_key,
    sa.assessment_id as assessment_id,
    o.offering_key as offering_key,
    sa.title as title,
    sa.weight_percentage as weight_percentage,
    sa.max_score as max_score,
    current_timestamp as _loaded_at
from {{ ref('stg_assessments') }} sa
left join {{ ref('dim_subject_offering') }} o
    on sa.offering_id = o.offering_id