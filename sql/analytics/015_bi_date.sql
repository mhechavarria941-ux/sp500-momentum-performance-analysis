/*
015_bi_date.sql

Fix bi.dim_date so it is a continuous calendar with one row per calendar day.

Version: 2026-08-31-v1
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW bi.dim_date
AS
WITH observed_dates AS
(
    SELECT session_date AS [date]
    FROM research.h4_daily_level

    UNION

    SELECT ranking_month_end_date
    FROM research.v_h1_monthly_performance

    UNION

    SELECT ranking_month_end_date
    FROM research.v_h2_primary_monthly

    UNION

    SELECT predictor_month_end
    FROM research.v_h3_panel

    UNION

    SELECT outcome_month_end
    FROM research.v_h3_panel
),
bounds AS
(
    SELECT
        MIN([date]) AS min_date,
        MAX([date]) AS max_date
    FROM observed_dates
    WHERE [date] IS NOT NULL
),
digits AS
(
    SELECT n
    FROM
    (
        VALUES
            (0),(1),(2),(3),(4),(5),(6),(7),(8),(9)
    ) AS d(n)
),
numbers AS
(
    SELECT
        d0.n
        + 10 * d1.n
        + 100 * d2.n
        + 1000 * d3.n AS n
    FROM digits AS d0
    CROSS JOIN digits AS d1
    CROSS JOIN digits AS d2
    CROSS JOIN digits AS d3
),
calendar AS
(
    SELECT
        DATEADD(DAY, n.n, b.min_date) AS [date]
    FROM bounds AS b
    CROSS JOIN numbers AS n
    WHERE
        b.min_date IS NOT NULL
        AND b.max_date IS NOT NULL
        AND DATEADD(DAY, n.n, b.min_date) <= b.max_date
)
SELECT
    [date],
    YEAR([date]) AS [year],
    DATEPART(QUARTER, [date]) AS quarter_number,
    CONCAT('Q', DATEPART(QUARTER, [date])) AS quarter_label,
    MONTH([date]) AS month_number,
    DATENAME(MONTH, [date]) AS month_name,
    CONVERT(char(7), [date], 126) AS year_month,
    DATEFROMPARTS(YEAR([date]), MONTH([date]), 1) AS month_start,
    EOMONTH([date]) AS month_end,
    DATEPART(ISO_WEEK, [date]) AS iso_week,
    DATENAME(WEEKDAY, [date]) AS weekday_name
FROM calendar;
GO
