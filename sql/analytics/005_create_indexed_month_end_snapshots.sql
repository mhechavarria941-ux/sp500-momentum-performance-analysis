SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(
    'analytics.security_month_end_snapshot',
    'U'
) IS NULL
BEGIN
    CREATE TABLE analytics.security_month_end_snapshot (
        analysis_month_number INT NOT NULL,
        month_start_date DATE NOT NULL,
        month_end_date DATE NOT NULL,
        security_key VARCHAR(32) NOT NULL,
        company_name_reference NVARCHAR(255) NOT NULL,
        project_ticker VARCHAR(32) NOT NULL,
        provider_symbol VARCHAR(32) NOT NULL,
        adjusted_close DECIMAL(38, 18) NOT NULL,
        membership_valid_from DATE NOT NULL,
        membership_valid_to_exclusive DATE NOT NULL,
        usable_start DATE NOT NULL,
        usable_end_exclusive DATE NOT NULL,
        snapshot_refreshed_at_utc DATETIME2(0) NOT NULL
            CONSTRAINT
                DF_security_month_end_snapshot_refreshed
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_security_month_end_snapshot
            PRIMARY KEY CLUSTERED (
                analysis_month_number,
                security_key
            ),

        CONSTRAINT
            FK_security_month_end_snapshot_security
            FOREIGN KEY (security_key)
            REFERENCES core.security (
                security_key
            ),

        CONSTRAINT
            FK_security_month_end_snapshot_ticker
            FOREIGN KEY (
                security_key,
                project_ticker
            )
            REFERENCES core.security_ticker_history (
                security_key,
                ticker
            ),

        CONSTRAINT
            CK_security_month_end_snapshot_month_number
            CHECK (
                analysis_month_number
                BETWEEN 1 AND 60
            ),

        CONSTRAINT
            CK_security_month_end_snapshot_price
            CHECK (adjusted_close > 0),

        CONSTRAINT
            CK_security_month_end_snapshot_membership
            CHECK (
                membership_valid_from
                    <= month_end_date
                AND membership_valid_to_exclusive
                    > month_end_date
            ),

        CONSTRAINT
            CK_security_month_end_snapshot_usable
            CHECK (
                usable_start <= month_end_date
                AND usable_end_exclusive
                    > month_end_date
            )
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(
        'analytics.security_month_end_snapshot'
    )
      AND name =
        'IX_security_month_end_snapshot_security_month'
)
BEGIN
    CREATE NONCLUSTERED INDEX
        IX_security_month_end_snapshot_security_month
    ON analytics.security_month_end_snapshot (
        security_key,
        analysis_month_number
    )
    INCLUDE (
        month_end_date,
        project_ticker,
        adjusted_close
    );
END;
GO

IF OBJECT_ID(
    'analytics.benchmark_month_end_snapshot',
    'U'
) IS NULL
BEGIN
    CREATE TABLE analytics.benchmark_month_end_snapshot (
        analysis_month_number INT NOT NULL,
        month_start_date DATE NOT NULL,
        month_end_date DATE NOT NULL,
        security_key VARCHAR(32) NOT NULL,
        project_ticker VARCHAR(32) NOT NULL,
        provider_symbol VARCHAR(32) NOT NULL,
        benchmark_name NVARCHAR(100) NOT NULL,
        series_type VARCHAR(32) NOT NULL,
        adjusted_close DECIMAL(38, 18) NOT NULL,
        snapshot_refreshed_at_utc DATETIME2(0) NOT NULL
            CONSTRAINT
                DF_benchmark_month_end_snapshot_refreshed
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_benchmark_month_end_snapshot
            PRIMARY KEY CLUSTERED (
                analysis_month_number,
                security_key,
                project_ticker
            ),

        CONSTRAINT
            FK_benchmark_month_end_snapshot_series
            FOREIGN KEY (
                security_key,
                project_ticker
            )
            REFERENCES core.benchmark_series (
                security_key,
                project_ticker
            ),

        CONSTRAINT
            CK_benchmark_month_end_snapshot_month_number
            CHECK (
                analysis_month_number
                BETWEEN 1 AND 60
            ),

        CONSTRAINT
            CK_benchmark_month_end_snapshot_price
            CHECK (adjusted_close > 0)
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(
        'analytics.benchmark_month_end_snapshot'
    )
      AND name =
        'IX_benchmark_month_end_snapshot_series_month'
)
BEGIN
    CREATE NONCLUSTERED INDEX
        IX_benchmark_month_end_snapshot_series_month
    ON analytics.benchmark_month_end_snapshot (
        security_key,
        project_ticker,
        analysis_month_number
    )
    INCLUDE (
        month_end_date,
        adjusted_close
    );
END;
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

    lag_1.month_end_date
        AS lag_1_month_end_date,

    lag_3.month_end_date
        AS lag_3_month_end_date,

    lag_6.month_end_date
        AS lag_6_month_end_date,

    lag_12.month_end_date
        AS lag_12_month_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_1.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_1m,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_3.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_3m,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_6.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_6m,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_12.adjusted_close
                    AS float
                )
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
                CAST(
                    lag_1.adjusted_close
                    AS float
                )
                / CAST(
                    lag_12.adjusted_close
                    AS float
                )
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

FROM analytics.security_month_end_snapshot
    AS current_price

LEFT JOIN analytics.security_month_end_snapshot
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.analysis_month_number
   = current_price.analysis_month_number - 1

LEFT JOIN analytics.security_month_end_snapshot
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.analysis_month_number
   = current_price.analysis_month_number - 3

LEFT JOIN analytics.security_month_end_snapshot
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.analysis_month_number
   = current_price.analysis_month_number - 6

LEFT JOIN analytics.security_month_end_snapshot
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

    lag_1.month_end_date
        AS lag_1_month_end_date,

    lag_3.month_end_date
        AS lag_3_month_end_date,

    lag_6.month_end_date
        AS lag_6_month_end_date,

    lag_12.month_end_date
        AS lag_12_month_end_date,

    CAST(
        CASE
            WHEN lag_1.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_1.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_1m,

    CAST(
        CASE
            WHEN lag_3.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_3.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_3m,

    CAST(
        CASE
            WHEN lag_6.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_6.adjusted_close
                    AS float
                )
                - 1.0
            ELSE NULL
        END
        AS decimal(38, 18)
    ) AS trailing_return_6m,

    CAST(
        CASE
            WHEN lag_12.security_key IS NOT NULL
            THEN
                CAST(
                    current_price.adjusted_close
                    AS float
                )
                / CAST(
                    lag_12.adjusted_close
                    AS float
                )
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
                CAST(
                    lag_1.adjusted_close
                    AS float
                )
                / CAST(
                    lag_12.adjusted_close
                    AS float
                )
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

FROM analytics.benchmark_month_end_snapshot
    AS current_price

LEFT JOIN analytics.benchmark_month_end_snapshot
    AS lag_1
  ON lag_1.security_key
   = current_price.security_key
 AND lag_1.project_ticker
   = current_price.project_ticker
 AND lag_1.analysis_month_number
   = current_price.analysis_month_number - 1

LEFT JOIN analytics.benchmark_month_end_snapshot
    AS lag_3
  ON lag_3.security_key
   = current_price.security_key
 AND lag_3.project_ticker
   = current_price.project_ticker
 AND lag_3.analysis_month_number
   = current_price.analysis_month_number - 3

LEFT JOIN analytics.benchmark_month_end_snapshot
    AS lag_6
  ON lag_6.security_key
   = current_price.security_key
 AND lag_6.project_ticker
   = current_price.project_ticker
 AND lag_6.analysis_month_number
   = current_price.analysis_month_number - 6

LEFT JOIN analytics.benchmark_month_end_snapshot
    AS lag_12
  ON lag_12.security_key
   = current_price.security_key
 AND lag_12.project_ticker
   = current_price.project_ticker
 AND lag_12.analysis_month_number
   = current_price.analysis_month_number - 12;
GO