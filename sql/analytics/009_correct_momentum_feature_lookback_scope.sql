/*
009_correct_momentum_feature_lookback_scope.sql

Purpose
-------
Correct the analytical lookback boundary for monthly trailing-return and 12-1
momentum features.

The ranking-date population remains the validated point-in-time S&P 500
month-end snapshot.  Historical lag anchors, however, are allowed to use the
validated standardized price history for the same permanent security identity,
including observations before S&P 500 membership.

The companion Python application transactionally loads exact SPY month-end
support observations for 2020-01 through 2025-12 into the two support tables
created below, then applies these views.

No core table is modified.
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(
    N'analytics.security_month_end_feature_support',
    N'U'
) IS NULL
BEGIN
    CREATE TABLE analytics.security_month_end_feature_support
    (
        feature_month_number INT NOT NULL,
        month_end_date DATE NOT NULL,
        security_key NVARCHAR(64) NOT NULL,
        project_ticker NVARCHAR(32) NOT NULL,
        adjusted_close DECIMAL(38, 18) NOT NULL,

        CONSTRAINT PK_security_month_end_feature_support
            PRIMARY KEY CLUSTERED
            (
                security_key,
                feature_month_number
            ),

        CONSTRAINT UQ_security_month_end_feature_support_date
            UNIQUE
            (
                security_key,
                month_end_date
            ),

        CONSTRAINT CK_security_month_end_feature_support_price
            CHECK (adjusted_close > 0)
    );

    CREATE INDEX IX_security_month_end_feature_support_month
        ON analytics.security_month_end_feature_support
        (
            feature_month_number,
            security_key
        )
        INCLUDE
        (
            month_end_date,
            adjusted_close,
            project_ticker
        );
END;

IF OBJECT_ID(
    N'analytics.benchmark_month_end_feature_support',
    N'U'
) IS NULL
BEGIN
    CREATE TABLE analytics.benchmark_month_end_feature_support
    (
        feature_month_number INT NOT NULL,
        month_end_date DATE NOT NULL,
        security_key NVARCHAR(64) NOT NULL,
        project_ticker NVARCHAR(32) NOT NULL,
        adjusted_close DECIMAL(38, 18) NOT NULL,

        CONSTRAINT PK_benchmark_month_end_feature_support
            PRIMARY KEY CLUSTERED
            (
                security_key,
                project_ticker,
                feature_month_number
            ),

        CONSTRAINT UQ_benchmark_month_end_feature_support_date
            UNIQUE
            (
                security_key,
                project_ticker,
                month_end_date
            ),

        CONSTRAINT CK_benchmark_month_end_feature_support_price
            CHECK (adjusted_close > 0)
    );

    CREATE INDEX IX_benchmark_month_end_feature_support_month
        ON analytics.benchmark_month_end_feature_support
        (
            feature_month_number,
            security_key,
            project_ticker
        )
        INCLUDE
        (
            month_end_date,
            adjusted_close
        );
END;
GO

/*
Current/ranking rows still come only from security_month_end_snapshot.
Only the lag source changes to the broader feature-support table.

feature_month_number uses the same monthly sequence as analysis_month_number:
    2020-01 = -11
    ...
    2020-12 = 0
    2021-01 = 1
    ...
    2025-12 = 60
*/
CREATE OR ALTER VIEW analytics.v_security_monthly_return_features
AS
SELECT
    current_price.*,

    lag_1.month_end_date
        AS lag_1_month_end_date,
    CASE
        WHEN lag_1.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_1.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_1m,
    CAST(
        CASE
            WHEN lag_1.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_1m_complete,

    lag_3.month_end_date
        AS lag_3_month_end_date,
    CASE
        WHEN lag_3.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_3.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_3m,
    CAST(
        CASE
            WHEN lag_3.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_3m_complete,

    lag_6.month_end_date
        AS lag_6_month_end_date,
    CASE
        WHEN lag_6.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_6.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_6m,
    CAST(
        CASE
            WHEN lag_6.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_6m_complete,

    lag_12.month_end_date
        AS lag_12_month_end_date,
    CASE
        WHEN lag_12.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_12.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_12m,
    CAST(
        CASE
            WHEN lag_12.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_12m_complete,

    lag_12.month_end_date
        AS momentum_12_1_start_date,
    lag_1.month_end_date
        AS momentum_12_1_end_date,
    CASE
        WHEN lag_1.security_key IS NULL
          OR lag_12.security_key IS NULL
            THEN NULL
        ELSE
            CAST(lag_1.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_12.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS momentum_12_1,
    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS momentum_12_1_complete
FROM analytics.security_month_end_snapshot
    AS current_price
LEFT JOIN analytics.security_month_end_feature_support
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.feature_month_number
   = current_price.analysis_month_number - 1
LEFT JOIN analytics.security_month_end_feature_support
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.feature_month_number
   = current_price.analysis_month_number - 3
LEFT JOIN analytics.security_month_end_feature_support
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.feature_month_number
   = current_price.analysis_month_number - 6
LEFT JOIN analytics.security_month_end_feature_support
    AS lag_12
  ON lag_12.security_key
   = current_price.security_key
 AND lag_12.feature_month_number
   = current_price.analysis_month_number - 12;
GO

/*
Benchmark current rows remain the validated 2021-2025 benchmark snapshot.
The support table contributes only historical lag anchors.
*/
CREATE OR ALTER VIEW analytics.v_benchmark_monthly_return_features
AS
SELECT
    current_price.*,

    lag_1.month_end_date
        AS lag_1_month_end_date,
    CASE
        WHEN lag_1.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_1.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_1m,
    CAST(
        CASE
            WHEN lag_1.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_1m_complete,

    lag_3.month_end_date
        AS lag_3_month_end_date,
    CASE
        WHEN lag_3.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_3.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_3m,
    CAST(
        CASE
            WHEN lag_3.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_3m_complete,

    lag_6.month_end_date
        AS lag_6_month_end_date,
    CASE
        WHEN lag_6.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_6.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_6m,
    CAST(
        CASE
            WHEN lag_6.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_6m_complete,

    lag_12.month_end_date
        AS lag_12_month_end_date,
    CASE
        WHEN lag_12.security_key IS NULL
            THEN NULL
        ELSE
            CAST(current_price.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_12.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS trailing_return_12m,
    CAST(
        CASE
            WHEN lag_12.security_key IS NULL THEN 0
            ELSE 1
        END
        AS BIT
    ) AS trailing_return_12m_complete,

    lag_12.month_end_date
        AS momentum_12_1_start_date,
    lag_1.month_end_date
        AS momentum_12_1_end_date,
    CASE
        WHEN lag_1.security_key IS NULL
          OR lag_12.security_key IS NULL
            THEN NULL
        ELSE
            CAST(lag_1.adjusted_close AS FLOAT)
            / NULLIF(CAST(lag_12.adjusted_close AS FLOAT), 0.0)
            - 1.0
    END AS momentum_12_1,
    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
             AND lag_12.security_key IS NOT NULL
                THEN 1
            ELSE 0
        END
        AS BIT
    ) AS momentum_12_1_complete
FROM analytics.benchmark_month_end_snapshot
    AS current_price
LEFT JOIN analytics.benchmark_month_end_feature_support
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.project_ticker
   = current_price.project_ticker
 AND lag_1.feature_month_number
   = current_price.analysis_month_number - 1
LEFT JOIN analytics.benchmark_month_end_feature_support
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.project_ticker
   = current_price.project_ticker
 AND lag_3.feature_month_number
   = current_price.analysis_month_number - 3
LEFT JOIN analytics.benchmark_month_end_feature_support
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.project_ticker
   = current_price.project_ticker
 AND lag_6.feature_month_number
   = current_price.analysis_month_number - 6
LEFT JOIN analytics.benchmark_month_end_feature_support
    AS lag_12
  ON lag_12.security_key
   = current_price.security_key
 AND lag_12.project_ticker
   = current_price.project_ticker
 AND lag_12.feature_month_number
   = current_price.analysis_month_number - 12;
GO

/*
Refresh downstream non-schema-bound views after the feature-view definition is
changed.  Their SQL logic remains unchanged; only the corrected upstream signal
population flows through them.
*/
DECLARE @view_name SYSNAME;

DECLARE refresh_cursor CURSOR LOCAL FAST_FORWARD FOR
SELECT view_name
FROM
(
    VALUES
        (1,  N'analytics.v_security_monthly_momentum_ranking'),
        (2,  N'analytics.v_security_monthly_momentum_portfolio'),
        (3,  N'analytics.v_momentum_decile_monthly_summary'),
        (4,  N'analytics.v_security_monthly_forward_return_1m'),
        (5,  N'analytics.v_benchmark_monthly_forward_return_1m'),
        (6,  N'analytics.v_momentum_decile_forward_return_1m'),
        (7,  N'analytics.v_momentum_long_short_forward_return_1m'),
        (8,  N'analytics.v_momentum_monthly_performance_1m'),
        (9,  N'analytics.v_momentum_monthly_return_panel'),
        (10, N'analytics.v_momentum_cumulative_wealth'),
        (11, N'analytics.v_momentum_wealth_drawdown'),
        (12, N'analytics.v_momentum_performance_summary'),
        (13, N'analytics.v_momentum_decile_turnover'),
        (14, N'analytics.v_momentum_turnover_summary')
) AS ordered_views(sort_order, view_name)
WHERE OBJECT_ID(view_name, N'V') IS NOT NULL
ORDER BY sort_order;

OPEN refresh_cursor;

FETCH NEXT FROM refresh_cursor INTO @view_name;

WHILE @@FETCH_STATUS = 0
BEGIN
    EXEC sys.sp_refreshview @view_name;
    FETCH NEXT FROM refresh_cursor INTO @view_name;
END;

CLOSE refresh_cursor;
DEALLOCATE refresh_cursor;
GO
