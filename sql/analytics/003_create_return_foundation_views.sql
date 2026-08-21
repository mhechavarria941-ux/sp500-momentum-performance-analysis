SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF SCHEMA_ID('analytics') IS NULL
    EXEC('CREATE SCHEMA analytics');
GO

CREATE OR ALTER VIEW analytics.v_spy_trading_calendar
AS
SELECT
    p.price_date,
    ROW_NUMBER() OVER (
        ORDER BY p.price_date
    ) AS trading_session_number,
    LAG(p.price_date) OVER (
        ORDER BY p.price_date
    ) AS previous_spy_session,
    LEAD(p.price_date) OVER (
        ORDER BY p.price_date
    ) AS next_spy_session
FROM core.daily_benchmark_price AS p
INNER JOIN core.benchmark_series AS b
    ON b.security_key = p.security_key
   AND b.project_ticker = p.project_ticker
WHERE b.project_ticker = 'SPY'
  AND b.series_type = 'ETF';
GO

CREATE OR ALTER VIEW analytics.v_spy_month_end_calendar
AS
WITH ranked_sessions AS (
    SELECT
        c.price_date,
        c.trading_session_number,
        DATEFROMPARTS(
            YEAR(c.price_date),
            MONTH(c.price_date),
            1
        ) AS month_start_date,
        ROW_NUMBER() OVER (
            PARTITION BY YEAR(c.price_date), MONTH(c.price_date)
            ORDER BY c.price_date DESC
        ) AS descending_session_number
    FROM analytics.v_spy_trading_calendar AS c
)
SELECT
    month_start_date,
    price_date AS month_end_date,
    YEAR(price_date) AS calendar_year,
    MONTH(price_date) AS calendar_month,
    DATEDIFF(
        MONTH,
        CONVERT(date, '20201201', 112),
        month_start_date
    ) AS analysis_month_number,
    trading_session_number
FROM ranked_sessions
WHERE descending_session_number = 1;
GO

CREATE OR ALTER VIEW analytics.v_security_daily_return
AS
WITH ordered_prices AS (
    SELECT
        p.security_key,
        p.project_ticker,
        p.provider_symbol,
        p.price_date,
        p.adjusted_close,
        LAG(p.price_date) OVER (
            PARTITION BY p.security_key
            ORDER BY p.price_date
        ) AS previous_price_date,
        LAG(p.project_ticker) OVER (
            PARTITION BY p.security_key
            ORDER BY p.price_date
        ) AS previous_project_ticker,
        LAG(p.adjusted_close) OVER (
            PARTITION BY p.security_key
            ORDER BY p.price_date
        ) AS previous_adjusted_close
    FROM core.daily_security_price AS p
)
SELECT
    p.security_key,
    p.project_ticker,
    p.provider_symbol,
    p.price_date,
    p.adjusted_close,
    p.previous_price_date,
    p.previous_project_ticker,
    p.previous_adjusted_close,
    c.previous_spy_session AS expected_previous_price_date,
    CAST(
        CASE
            WHEN p.previous_price_date = c.previous_spy_session
             AND p.previous_adjusted_close > 0
            THEN
                CAST(p.adjusted_close AS float)
                / CAST(p.previous_adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS daily_return,
    CAST(
        CASE
            WHEN p.previous_price_date = c.previous_spy_session
             AND p.previous_adjusted_close > 0
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS daily_return_complete
FROM ordered_prices AS p
INNER JOIN analytics.v_spy_trading_calendar AS c
    ON c.price_date = p.price_date;
GO

CREATE OR ALTER VIEW analytics.v_benchmark_daily_return
AS
WITH ordered_prices AS (
    SELECT
        p.security_key,
        p.project_ticker,
        p.provider_symbol,
        b.benchmark_name,
        b.series_type,
        p.price_date,
        p.adjusted_close,
        LAG(p.price_date) OVER (
            PARTITION BY p.security_key, p.project_ticker
            ORDER BY p.price_date
        ) AS previous_price_date,
        LAG(p.adjusted_close) OVER (
            PARTITION BY p.security_key, p.project_ticker
            ORDER BY p.price_date
        ) AS previous_adjusted_close
    FROM core.daily_benchmark_price AS p
    INNER JOIN core.benchmark_series AS b
        ON b.security_key = p.security_key
       AND b.project_ticker = p.project_ticker
)
SELECT
    p.security_key,
    p.project_ticker,
    p.provider_symbol,
    p.benchmark_name,
    p.series_type,
    p.price_date,
    p.adjusted_close,
    p.previous_price_date,
    p.previous_adjusted_close,
    c.previous_spy_session AS expected_previous_price_date,
    CAST(
        CASE
            WHEN p.previous_price_date = c.previous_spy_session
             AND p.previous_adjusted_close > 0
            THEN
                CAST(p.adjusted_close AS float)
                / CAST(p.previous_adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS daily_return,
    CAST(
        CASE
            WHEN p.previous_price_date = c.previous_spy_session
             AND p.previous_adjusted_close > 0
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS daily_return_complete
FROM ordered_prices AS p
INNER JOIN analytics.v_spy_trading_calendar AS c
    ON c.price_date = p.price_date;
GO

CREATE OR ALTER VIEW analytics.v_security_month_end_price
AS
SELECT
    c.analysis_month_number,
    c.month_start_date,
    c.month_end_date,
    p.security_key,
    s.company_name_reference,
    p.project_ticker,
    p.provider_symbol,
    p.adjusted_close,
    m.valid_from AS membership_valid_from,
    m.valid_to_exclusive AS membership_valid_to_exclusive,
    e.usable_start,
    e.usable_end_exclusive
FROM analytics.v_spy_month_end_calendar AS c
INNER JOIN core.daily_security_price AS p
    ON p.price_date = c.month_end_date
INNER JOIN core.security AS s
    ON s.security_key = p.security_key
INNER JOIN core.index_membership AS m
    ON m.index_code = 'SP500'
   AND m.security_key = p.security_key
   AND m.valid_from <= p.price_date
   AND m.valid_to_exclusive > p.price_date
INNER JOIN core.security_price_eligibility AS e
    ON e.security_key = p.security_key
   AND e.project_ticker = p.project_ticker
   AND e.usable_start <= p.price_date
   AND e.usable_end_exclusive > p.price_date;
GO

CREATE OR ALTER VIEW analytics.v_benchmark_month_end_price
AS
SELECT
    c.analysis_month_number,
    c.month_start_date,
    c.month_end_date,
    p.security_key,
    p.project_ticker,
    p.provider_symbol,
    b.benchmark_name,
    b.series_type,
    p.adjusted_close
FROM analytics.v_spy_month_end_calendar AS c
INNER JOIN core.daily_benchmark_price AS p
    ON p.price_date = c.month_end_date
INNER JOIN core.benchmark_series AS b
    ON b.security_key = p.security_key
   AND b.project_ticker = p.project_ticker;
GO