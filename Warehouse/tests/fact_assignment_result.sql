-- raw_score must be between 0 and 200

select
    *
from 
    {{ref('fact_assessment_result') }} 
where 
    raw_score < 0
    or raw_score > 200
