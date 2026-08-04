with base as (
    select
        fpe.program_enrollment_key,
        fpe.program_key,
        fpe.status,
        extract(year from fpe.enrollment_date)::int as cohort_year,
        ope.program_gpa,
        ope.actual_duration_years
    from {{ ref('fact_program_enrollment') }} fpe
    left join {{ ref('obt_program_enrollment') }} ope
        on fpe.program_enrollment_key = ope.program_enrollment_key
)

select
    hash(dp.program_id, b.cohort_year) as program_summary_key,
    dp.program_id, dp.program_name, dp.department, dp.degree_level,
    b.cohort_year,
    count(distinct b.program_enrollment_key) as total_enrolled_students,
    count(distinct case when b.status = 'Active' then b.program_enrollment_key end) as total_active_students,
    count(distinct case when b.status = 'Graduated' then b.program_enrollment_key end) as total_graduated_students,
    count(distinct case when b.status in ('Withdrawn', 'Dismissed') then b.program_enrollment_key end) as total_withdrawn_students,
    round(avg(b.program_gpa), 2) as average_gpa,
    round(
        count(distinct case when b.status in ('Active', 'Graduated') then b.program_enrollment_key end)::decimal
            / nullif(count(distinct b.program_enrollment_key), 0), 2
    ) as retention_rate,
    round(
        count(distinct case when b.status = 'Graduated' then b.program_enrollment_key end)::decimal
            / nullif(count(distinct b.program_enrollment_key), 0), 2
    ) as graduation_rate,
    round(avg(case when b.status = 'Graduated' then b.actual_duration_years end), 2) as average_time_to_degree_years,
    current_timestamp as _loaded_at
from base b
join {{ ref('dim_program') }} dp on b.program_key = dp.program_key
group by dp.program_id, dp.program_name, dp.department, dp.degree_level, b.cohort_year