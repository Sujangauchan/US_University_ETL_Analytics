with enriched as (
    select
        far.result_key,
        far.result_id,
        far.subject_enrollment_key,
        far.assessment_key,
        far.raw_score,
        far.submitted_at,
        ds.student_id, ds.first_name, ds.last_name,
        dsub.subject_code, dsub.subject_title,
        dsem.semester_id, dsem.semester_name, dsem.academic_year,
        da.title as assessment_title, da.weight_percentage, da.max_score,
        fse.final_mark, fse.final_grade
    from {{ ref('fact_assessment_result') }} far
    left join {{ ref('dim_student') }} ds on far.student_key = ds.student_key
    left join {{ ref('dim_assessment') }} da on far.assessment_key = da.assessment_key
    left join {{ ref('dim_subject_offering') }} dso on da.offering_key = dso.offering_key
    left join {{ ref('dim_subject') }} dsub on dso.subject_key = dsub.subject_key
    left join {{ ref('dim_semester') }} dsem on dso.semester_key = dsem.semester_key
    left join {{ ref('fact_subject_enrollment') }} fse on far.subject_enrollment_key = fse.subject_enrollment_key
),

scored as (
    select *, raw_score / nullif(max_score, 0) as score_percentage
    from enriched
),

assessment_stats as (
    select
        assessment_key,
        avg(raw_score) as assessment_average_score_for_offering,
        stddev(raw_score) as assessment_stddev,
        avg(case when (raw_score / nullif(max_score, 0)) >= {{ var('pass_threshold_pct') }}
                 then 1.0 else 0.0 end) as assessment_pass_rate
    from scored
    group by assessment_key
),

trend as (
    select
        result_key,
        lag(score_percentage) over (partition by subject_enrollment_key order by submitted_at) as prev_score_percentage
    from scored
)

select
    s.result_key, s.result_id,
    s.student_id, s.first_name, s.last_name,
    s.subject_code, s.subject_title,
    s.semester_id, s.semester_name, s.academic_year,
    s.assessment_title, s.weight_percentage, s.max_score,
    s.raw_score, s.submitted_at,
    s.final_mark, s.final_grade,
    s.score_percentage,
    round(s.score_percentage * s.weight_percentage, 2) as weighted_contribution,
    ast.assessment_average_score_for_offering,
    ast.assessment_pass_rate,
    case when ast.assessment_stddev is null or ast.assessment_stddev = 0 then null
         else (s.raw_score - ast.assessment_average_score_for_offering) / ast.assessment_stddev
    end as z_score_within_assessment,
    case
        when s.score_percentage >= {{ var('score_band_excellent_pct') }} then 'Excellent'
        when s.score_percentage >= {{ var('score_band_satisfactory_pct') }} then 'Satisfactory'
        when s.score_percentage >= {{ var('pass_threshold_pct') }} then 'Needs Improvement'
        else 'Fail'
    end as score_band,
    case
        when t.prev_score_percentage is null then 'First'
        when s.score_percentage > t.prev_score_percentage then 'Improving'
        when s.score_percentage < t.prev_score_percentage then 'Declining'
        else 'Stable'
    end as mark_trend_within_subject,
    current_timestamp as _loaded_at
from scored s
left join assessment_stats ast on s.assessment_key = ast.assessment_key
left join trend t on s.result_key = t.result_key