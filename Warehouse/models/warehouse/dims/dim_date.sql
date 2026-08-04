with date_spine as (
    select
        unnest(generate_series(
            '2000-01-01'::date,
            '2035-12-31'::date,
            interval '1 day'
        ))::date as date_day
)

select
    -- Full Date
    date_day as full_date,

    -- Year Components (as ints)
    extract(year from date_day)::int as year,
    extract(quarter from date_day)::int as quarter,
    extract(month from date_day)::int as month,

    -- Month Name
    case 
        when extract(month from date_day)::int = 1 then 'January'
        when extract(month from date_day)::int = 2 then 'February'
        when extract(month from date_day)::int = 3 then 'March'
        when extract(month from date_day)::int = 4 then 'April'
        when extract(month from date_day)::int = 5 then 'May'
        when extract(month from date_day)::int = 6 then 'June'
        when extract(month from date_day)::int = 7 then 'July'
        when extract(month from date_day)::int = 8 then 'August'
        when extract(month from date_day)::int = 9 then 'September'
        when extract(month from date_day)::int = 10 then 'October'
        when extract(month from date_day)::int = 11 then 'November'
        else 'December'
    end as month_name,

    -- Day of Week
    extract(dow from date_day)::int as day_of_week,

    -- Day Name
    case 
        when extract(dow from date_day)::int = 0 then 'Sunday'
        when extract(dow from date_day)::int = 1 then 'Monday'
        when extract(dow from date_day)::int = 2 then 'Tuesday'
        when extract(dow from date_day)::int = 3 then 'Wednesday'
        when extract(dow from date_day)::int = 4 then 'Thursday'
        when extract(dow from date_day)::int = 5 then 'Friday'
        else 'Saturday'
    end as day_name,

    -- Is Weekend? (True if Saturday or Sunday)
    case 
        when extract(dow from date_day)::int in (0, 6) then true 
        else false 
    end as is_weekend,

    -- Day of month
    extract(day from date_day)::int as day_of_month,

    -- ISO week number
    extract(week from date_day)::int as iso_week,

    -- Month / Quarter start dates
    date_trunc('month', date_day)::date as month_start,
    date_trunc('quarter', date_day)::date as quarter_start,

    -- Fiscal Year using July 1 - June 30 (common in US universities)
    case 
        when extract(month from date_day)::int >= 7 
        then extract(year from date_day)::int + 1
        else extract(year from date_day)::int
    end as fiscal_year

from date_spine