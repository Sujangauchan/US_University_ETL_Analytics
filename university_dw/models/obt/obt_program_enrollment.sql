with subject_agg as (
    select
        program_enrollment_key,
        sum(attempt_number - 1) as total_retakes,
        sum(credit_points_earned) as credits_earned,
        sum(case when final_mark is not null then final_mark * credit_points else 0 end)
            / nullif(sum(case when final_mark is not null then credit_points else 0 end), 0) as program_gpa
    from {{ ref('obt_subject_enrollment') }}
    group by program_enrollment_key
),

last_activity as (
    select
        fse.program_enrollment_key,
        max(far.submitted_at) as last_activity_at
    from {{ ref('fact_subject_enrollment') }} fse
    left join {{ ref('fact_assessment_result') }} far
        on fse.subject_enrollment_key = far.subject_enrollment_key
    group by fse.program_enrollment_key
),

multi_program as (
    select student_key, count(distinct program_enrollment_id) as program_count
    from {{ ref('fact_program_enrollment') }}
    group by student_key
)

select
    fpe.program_enrollment_key,
    fpe.program_enrollment_id,
    ds.student_id, ds.first_name, ds.last_name, ds.email,
    dp.program_id, dp.program_name, dp.department, dp.degree_level, dp.total_credit_points_required,
    fpe.enrollment_date,
    fpe.completion_date,
    fpe.status,
    fpe.final_degree_result,

    extract(year from fpe.enrollment_date)::int as cohort_year,

    extract(year from age(coalesce(fpe.completion_date, current_date), fpe.enrollment_date))::int + 1
        as current_year_of_study,

    round(date_diff('day', fpe.enrollment_date, coalesce(fpe.completion_date, current_date)) / 365.25, 2)
        as actual_duration_years,

    fpe.enrollment_date + (
        case dp.degree_level
            when 'Bachelor''s' then interval '4 years'
            when 'Master''s'   then interval '2 years'
            when 'Doctoral'    then interval '5 years'
            else interval '4 years'
        end
    ) as expected_graduation_date,

    round(100.0 * sa.credits_earned / nullif(dp.total_credit_points_required, 0), 2)
        as credits_completed_percentage,

    round(sa.program_gpa, 2) as program_gpa,

    coalesce(sa.total_retakes, 0) as total_retakes,
    coalesce(sa.total_retakes, 0) > {{ var('retake_heavy_threshold') }} as is_retake_heavy,

    coalesce(mp.program_count, 1) > 1 as is_multi_program_student,

    date_diff('day', coalesce(la.last_activity_at, fpe.enrollment_date)::date, current_date)
        as days_since_last_activity,

    case
        when sa.program_gpa is null then null
        when sa.program_gpa >= {{ var('good_standing_gpa') }} then 'Good Standing'
        when sa.program_gpa >= {{ var('at_risk_gpa') }} then 'Probation'
        else 'At Risk'
    end as academic_standing,

    -- only flags currently-active students as "at risk" — a graduated/withdrawn student isn't ongoing risk
    (
        date_diff('day', coalesce(la.last_activity_at, fpe.enrollment_date)::date, current_date)
            > {{ var('at_risk_inactivity_days') }}
        or coalesce(sa.program_gpa, 100) < {{ var('at_risk_gpa') }}
    ) and fpe.status = 'Active' as is_at_risk,

    current_timestamp as _loaded_at

from {{ ref('fact_program_enrollment') }} fpe
left join {{ ref('dim_student') }} ds on fpe.student_key = ds.student_key
left join {{ ref('dim_program') }} dp on fpe.program_key = dp.program_key
left join subject_agg sa on fpe.program_enrollment_key = sa.program_enrollment_key
left join last_activity la on fpe.program_enrollment_key = la.program_enrollment_key
left join multi_program mp on fpe.student_key = mp.student_key