SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW
    analytics.v_security_monthly_return_features
AS
SELECT
    current_price.analysis_month_number,
    current_price.month_start_date,
    current_price.month_end_date,
    current_price.security_key,
    current_price.company_name_reference,
    current_price.project_ticker,
    current_price.provider_symbol,
    current_price.adjusted_close,
    current_price.membership_valid_from,
    current_price.membership_valid_to_exclusive,
    current_price.usable_start,
    current_price.usable_end_exclusive,
    lag_1.month_end_date AS lag_1_month_end_date,
    lag_3.month_end_date AS lag_3_month_end_date,
    lag_6.month_end_date AS lag_6_month_end_date,
    lag_12.month_end_date AS lag_12_month_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_1.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_1m,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_3.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_3m,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_6.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_6m,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_12.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_12m,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_1m_complete,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_3m_complete,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_6m_complete,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_12m_complete,

    lag_12.month_end_date
        AS momentum_12_1_start_date,

    lag_1.month_end_date
        AS momentum_12_1_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
            THEN
                CAST(lag_1.adjusted_close AS float)
                / CAST(lag_12.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS momentum_12_1,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS momentum_12_1_complete

FROM analytics.v_security_month_end_price
    AS current_price

LEFT JOIN analytics.v_security_month_end_price
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.analysis_month_number
   = current_price.analysis_month_number - 1

LEFT JOIN analytics.v_security_month_end_price
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.analysis_month_number
   = current_price.analysis_month_number - 3

LEFT JOIN analytics.v_security_month_end_price
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.analysis_month_number
   = current_price.analysis_month_number - 6

LEFT JOIN analytics.v_security_month_end_price
    AS lag_12
  ON lag_12.security_key
   = current_price.security_key
 AND lag_12.analysis_month_number
   = current_price.analysis_month_number - 12;
GO

CREATE OR ALTER VIEW
    analytics.v_benchmark_monthly_return_features
AS
SELECT
    current_price.analysis_month_number,
    current_price.month_start_date,
    current_price.month_end_date,
    current_price.security_key,
    current_price.project_ticker,
    current_price.provider_symbol,
    current_price.benchmark_name,
    current_price.series_type,
    current_price.adjusted_close,
    lag_1.month_end_date AS lag_1_month_end_date,
    lag_3.month_end_date AS lag_3_month_end_date,
    lag_6.month_end_date AS lag_6_month_end_date,
    lag_12.month_end_date AS lag_12_month_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_1.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_1m,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_3.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_3m,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_6.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_6m,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN
                CAST(current_price.adjusted_close AS float)
                / CAST(lag_12.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_12m,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_1m_complete,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_3m_complete,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_6m_complete,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS trailing_return_12m_complete,

    lag_12.month_end_date
        AS momentum_12_1_start_date,

    lag_1.month_end_date
        AS momentum_12_1_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
            THEN
                CAST(lag_1.adjusted_close AS float)
                / CAST(lag_12.adjusted_close AS float)
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS momentum_12_1,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
            THEN 1
            ELSE 0
        END
        AS bit
    ) AS momentum_12_1_complete

FROM analytics.v_benchmark_month_end_price
    AS current_price

LEFT JOIN analytics.v_benchmark_month_end_price
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.project_ticker
   = current_price.project_ticker
 AND lag_1.analysis_month_number
   = current_price.analysis_month_number - 1

LEFT JOIN analytics.v_benchmark_month_end_price
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.project_ticker
   = current_price.project_ticker
 AND lag_3.analysis_month_number
   = current_price.analysis_month_number - 3

LEFT JOIN analytics.v_benchmark_month_end_price
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.project_ticker
   = current_price.project_ticker
 AND lag_6.analysis_month_number
   = current_price.analysis_month_number - 6

LEFT JOIN analytics.v_benchmark_month_end_price
    AS lag_12
  ON lag_12.security_key
   = current_price.security_key
 AND lag_12.project_ticker
   = current_price.project_ticker
 AND lag_12.analysis_month_number
   = current_price.analysis_month_number - 12;
GO