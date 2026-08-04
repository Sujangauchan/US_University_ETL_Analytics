select *
from 
    {{ ref('fact_program_enrollment') }}
where 
    enrollment_date > completion_date
    or status not in ('Active', 'Graduated', 'Withdrawn', 'Suspended', 'Dismissed', 'Leave of Absence')
    or program_enrollment_id is null
    or student_key is null
    or final_degree_result not in ('High Distinction', 'Distinction', 'Merit', 'Pass')