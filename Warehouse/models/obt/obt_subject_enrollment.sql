with enriched as (
    select
        fse.subject_enrollment_key,
        fse.subject_enrollment_id,
        fse.program_enrollment_key,
        fse.offering_key,
        fse.status,
        fse.final_mark,
        fse.final_grade,
        ds.student_id, ds.first_name, ds.last_name,
        dp.program_id, dp.program_name,
        dso.offering_id, dso.coordinator_name, dso.subject_key,
        dsub.subject_code, dsub.subject_title, dsub.credit_points,
        dsem.semester_id, dsem.semester_name, dsem.academic_year, dsem.start_date as semester_start_date
    from {{ ref('fact_subject_enrollment') }} fse
    left join {{ ref('dim_student') }} ds on fse.student_key = ds.student_key
    left join {{ ref('dim_program') }} dp on fse.program_key = dp.program_key
    left join {{ ref('dim_subject_offering') }} dso on fse.offering_key = dso.offering_key
    left join {{ ref('dim_subject') }} dsub on dso.subject_key = dsub.subject_key
    left join {{ ref('dim_semester') }} dsem on dso.semester_key = dsem.semester_key
),

windowed as (
    select
        *,
        row_number() over (
            partition by program_enrollment_key, subject_code
            order by semester_start_date
        ) as attempt_number,
        rank() over (partition by offering_key order by final_mark desc) as rank_in_offering
    from enriched
),

class_sizes as (
    select offering_key, count(*) as class_size
    from enriched group by offering_key
),

subject_stats as (
    select
        subject_code,
        semester_id,
        avg(final_mark) as program_average_mark_for_this_subject,
        avg(case when final_mark >= 50 then 1.0 else 0.0 end) as subject_pass_rate
    from enriched
    where final_mark is not null
    group by subject_code, semester_id
),

coordinator_stats as (
    select coordinator_name, avg(final_mark) as coordinator_average_mark
    from enriched
    where final_mark is not null
    group by coordinator_name
)

select
    w.subject_enrollment_key,
    w.subject_enrollment_id,
    w.program_enrollment_key,
    w.student_id, w.first_name, w.last_name,
    w.program_id, w.program_name,
    w.offering_id, w.coordinator_name,
    w.subject_code, w.subject_title, w.credit_points,
    w.semester_id, w.semester_name, w.academic_year,
    w.status, w.final_mark, w.final_grade,
    w.attempt_number,
    w.attempt_number > 1 as is_retake,
    (w.final_mark is not null and w.final_mark >= 50) as is_pass,
    case when (w.final_mark is not null and w.final_mark >= 50)
         then w.credit_points else 0 end as credit_points_earned,
    cs.class_size,
    ss.program_average_mark_for_this_subject,
    ss.subject_pass_rate,
    w.rank_in_offering,
    co.coordinator_average_mark,
    current_timestamp as _loaded_at
from windowed w
left join class_sizes cs on w.offering_key = cs.offering_key
left join subject_stats ss on w.subject_code = ss.subject_code and w.semester_id = ss.semester_id
left join coordinator_stats co on w.coordinator_name = co.coordinator_name