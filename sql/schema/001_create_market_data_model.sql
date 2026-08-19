SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF SCHEMA_ID('staging') IS NULL
        EXEC('CREATE SCHEMA staging');

    IF SCHEMA_ID('core') IS NULL
        EXEC('CREATE SCHEMA core');

    IF OBJECT_ID('core.market_index', 'U') IS NULL
    BEGIN
        CREATE TABLE core.market_index (
            index_code VARCHAR(20) NOT NULL,
            index_name NVARCHAR(100) NOT NULL,
            index_provider NVARCHAR(100) NOT NULL,
            analysis_start DATE NOT NULL,
            analysis_end DATE NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_market_index_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_market_index
                PRIMARY KEY CLUSTERED (index_code),
            CONSTRAINT CK_market_index_dates
                CHECK (analysis_start <= analysis_end)
        );
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM core.market_index
        WHERE index_code = 'SP500'
    )
    BEGIN
        INSERT INTO core.market_index (
            index_code,
            index_name,
            index_provider,
            analysis_start,
            analysis_end
        )
        VALUES (
            'SP500',
            N'S&P 500',
            N'S&P Dow Jones Indices',
            '2021-01-01',
            '2025-12-31'
        );
    END;

    IF OBJECT_ID('core.security', 'U') IS NULL
    BEGIN
        CREATE TABLE core.security (
            security_key VARCHAR(32) NOT NULL,
            company_name_reference NVARCHAR(255) NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_security_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_security
                PRIMARY KEY CLUSTERED (security_key),
            CONSTRAINT CK_security_key_not_blank
                CHECK (LEN(LTRIM(RTRIM(security_key))) > 0),
            CONSTRAINT CK_security_name_not_blank
                CHECK (
                    LEN(
                        LTRIM(
                            RTRIM(company_name_reference)
                        )
                    ) > 0
                )
        );
    END;

    IF OBJECT_ID(
        'core.security_ticker_history',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.security_ticker_history (
            security_key VARCHAR(32) NOT NULL,
            ticker VARCHAR(32) NOT NULL,
            ticker_valid_from DATE NOT NULL,
            ticker_valid_to_exclusive DATE NOT NULL,
            left_censored BIT NOT NULL,
            right_censored BIT NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_ticker_history_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_security_ticker_history
                PRIMARY KEY CLUSTERED (
                    security_key,
                    ticker_valid_from
                ),
            CONSTRAINT UQ_security_ticker_pair
                UNIQUE (
                    security_key,
                    ticker
                ),
            CONSTRAINT FK_ticker_history_security
                FOREIGN KEY (security_key)
                REFERENCES core.security (
                    security_key
                ),
            CONSTRAINT CK_ticker_history_dates
                CHECK (
                    ticker_valid_from
                    < ticker_valid_to_exclusive
                ),
            CONSTRAINT CK_ticker_not_blank
                CHECK (
                    LEN(
                        LTRIM(
                            RTRIM(ticker)
                        )
                    ) > 0
                )
        );
    END;

    IF OBJECT_ID(
        'core.index_membership',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.index_membership (
            index_code VARCHAR(20) NOT NULL,
            security_key VARCHAR(32) NOT NULL,
            valid_from DATE NOT NULL,
            valid_to_exclusive DATE NOT NULL,
            left_censored BIT NOT NULL,
            right_censored BIT NOT NULL,
            entry_ticker VARCHAR(32) NOT NULL,
            entry_source_url NVARCHAR(2048) NULL,
            exit_ticker VARCHAR(32) NULL,
            exit_source_url NVARCHAR(2048) NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_index_membership_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_index_membership
                PRIMARY KEY CLUSTERED (
                    index_code,
                    security_key,
                    valid_from
                ),
            CONSTRAINT FK_index_membership_index
                FOREIGN KEY (index_code)
                REFERENCES core.market_index (
                    index_code
                ),
            CONSTRAINT FK_index_membership_security
                FOREIGN KEY (security_key)
                REFERENCES core.security (
                    security_key
                ),
            CONSTRAINT FK_index_membership_entry_ticker
                FOREIGN KEY (
                    security_key,
                    entry_ticker
                )
                REFERENCES core.security_ticker_history (
                    security_key,
                    ticker
                ),
            CONSTRAINT FK_index_membership_exit_ticker
                FOREIGN KEY (
                    security_key,
                    exit_ticker
                )
                REFERENCES core.security_ticker_history (
                    security_key,
                    ticker
                ),
            CONSTRAINT CK_index_membership_dates
                CHECK (
                    valid_from < valid_to_exclusive
                ),
            CONSTRAINT CK_index_membership_entry_source
                CHECK (
                    (
                        left_censored = 1
                        AND entry_source_url IS NULL
                    )
                    OR
                    (
                        left_censored = 0
                        AND entry_source_url IS NOT NULL
                    )
                ),
            CONSTRAINT CK_index_membership_exit_fields
                CHECK (
                    (
                        right_censored = 1
                        AND exit_ticker IS NULL
                        AND exit_source_url IS NULL
                    )
                    OR
                    (
                        right_censored = 0
                        AND exit_ticker IS NOT NULL
                        AND exit_source_url IS NOT NULL
                    )
                )
        );
    END;

    IF OBJECT_ID(
        'core.security_price_eligibility',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.security_price_eligibility (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            effective_price_start DATE NOT NULL,
            effective_price_end_exclusive DATE NOT NULL,
            usable_start DATE NOT NULL,
            usable_end_exclusive DATE NOT NULL,
            standardized_rows INT NOT NULL,
            bridge_rows INT NOT NULL,
            rows_before_usable_window INT NOT NULL,
            rows_after_usable_window INT NOT NULL,
            first_bridge_date DATE NOT NULL,
            last_bridge_date DATE NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_price_eligibility_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_security_price_eligibility
                PRIMARY KEY CLUSTERED (
                    security_key,
                    project_ticker
                ),
            CONSTRAINT FK_price_eligibility_ticker
                FOREIGN KEY (
                    security_key,
                    project_ticker
                )
                REFERENCES core.security_ticker_history (
                    security_key,
                    ticker
                ),
            CONSTRAINT CK_price_eligibility_effective_dates
                CHECK (
                    effective_price_start
                    < effective_price_end_exclusive
                ),
            CONSTRAINT CK_price_eligibility_usable_dates
                CHECK (
                    usable_start < usable_end_exclusive
                ),
            CONSTRAINT CK_price_eligibility_counts
                CHECK (
                    standardized_rows > 0
                    AND bridge_rows > 0
                    AND rows_before_usable_window >= 0
                    AND rows_after_usable_window >= 0
                    AND standardized_rows =
                        bridge_rows
                        + rows_before_usable_window
                        + rows_after_usable_window
                ),
            CONSTRAINT CK_price_eligibility_first_date
                CHECK (
                    first_bridge_date >= usable_start
                    AND first_bridge_date
                        < usable_end_exclusive
                ),
            CONSTRAINT CK_price_eligibility_last_date
                CHECK (
                    last_bridge_date
                        >= first_bridge_date
                    AND last_bridge_date
                        < usable_end_exclusive
                )
        );
    END;

    IF OBJECT_ID(
        'core.daily_security_price',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.daily_security_price (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            price_date DATE NOT NULL,
            [open] DECIMAL(38, 18) NOT NULL,
            high DECIMAL(38, 18) NOT NULL,
            low DECIMAL(38, 18) NOT NULL,
            [close] DECIMAL(38, 18) NOT NULL,
            adjusted_close DECIMAL(38, 18) NOT NULL,
            volume BIGINT NOT NULL,
            dividend DECIMAL(38, 18) NOT NULL,
            split_factor DECIMAL(38, 18) NOT NULL,
            source VARCHAR(64) NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_daily_security_price_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_daily_security_price
                PRIMARY KEY CLUSTERED (
                    price_date,
                    security_key,
                    project_ticker
                ),
            CONSTRAINT FK_daily_security_price_eligibility
                FOREIGN KEY (
                    security_key,
                    project_ticker
                )
                REFERENCES core.security_price_eligibility (
                    security_key,
                    project_ticker
                ),
            CONSTRAINT CK_daily_security_price_positive
                CHECK (
                    [open] > 0
                    AND high > 0
                    AND low > 0
                    AND [close] > 0
                    AND adjusted_close > 0
                ),
            CONSTRAINT CK_daily_security_price_high
                CHECK (
                    high >= [open]
                    AND high >= low
                    AND high >= [close]
                ),
            CONSTRAINT CK_daily_security_price_low
                CHECK (
                    low <= [open]
                    AND low <= high
                    AND low <= [close]
                ),
            CONSTRAINT CK_daily_security_price_actions
                CHECK (
                    volume >= 0
                    AND dividend >= 0
                    AND split_factor > 0
                )
        );
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id =
            OBJECT_ID(
                'core.daily_security_price'
            )
          AND name =
            'IX_daily_security_price_security_date'
    )
    BEGIN
        CREATE NONCLUSTERED INDEX
            IX_daily_security_price_security_date
        ON core.daily_security_price (
            security_key,
            project_ticker,
            price_date
        )
        INCLUDE (
            adjusted_close,
            [close],
            volume
        );
    END;

    IF OBJECT_ID(
        'core.benchmark_series',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.benchmark_series (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            benchmark_name NVARCHAR(100) NOT NULL,
            series_type VARCHAR(32) NOT NULL,
            source VARCHAR(64) NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_benchmark_series_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_benchmark_series
                PRIMARY KEY CLUSTERED (
                    security_key,
                    project_ticker
                ),
            CONSTRAINT CK_benchmark_series_type
                CHECK (
                    series_type IN (
                        'INDEX',
                        'ETF'
                    )
                )
        );
    END;

    IF OBJECT_ID(
        'core.daily_benchmark_price',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE core.daily_benchmark_price (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            price_date DATE NOT NULL,
            [open] DECIMAL(38, 18) NOT NULL,
            high DECIMAL(38, 18) NOT NULL,
            low DECIMAL(38, 18) NOT NULL,
            [close] DECIMAL(38, 18) NOT NULL,
            adjusted_close DECIMAL(38, 18) NOT NULL,
            volume BIGINT NOT NULL,
            dividend DECIMAL(38, 18) NOT NULL,
            split_factor DECIMAL(38, 18) NOT NULL,
            source VARCHAR(64) NOT NULL,
            created_at_utc DATETIME2(0) NOT NULL
                CONSTRAINT DF_daily_benchmark_price_created_at_utc
                DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_daily_benchmark_price
                PRIMARY KEY CLUSTERED (
                    price_date,
                    security_key,
                    project_ticker
                ),
            CONSTRAINT FK_daily_benchmark_price_series
                FOREIGN KEY (
                    security_key,
                    project_ticker
                )
                REFERENCES core.benchmark_series (
                    security_key,
                    project_ticker
                ),
            CONSTRAINT CK_daily_benchmark_price_positive
                CHECK (
                    [open] > 0
                    AND high > 0
                    AND low > 0
                    AND [close] > 0
                    AND adjusted_close > 0
                ),
            CONSTRAINT CK_daily_benchmark_price_high
                CHECK (
                    high >= [open]
                    AND high >= low
                    AND high >= [close]
                ),
            CONSTRAINT CK_daily_benchmark_price_low
                CHECK (
                    low <= [open]
                    AND low <= high
                    AND low <= [close]
                ),
            CONSTRAINT CK_daily_benchmark_price_actions
                CHECK (
                    volume >= 0
                    AND dividend >= 0
                    AND split_factor > 0
                )
        );
    END;

    IF OBJECT_ID(
        'staging.security',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.security (
            security_key VARCHAR(32) NOT NULL,
            company_name_reference NVARCHAR(255)
                NOT NULL
        );
    END;

    IF OBJECT_ID(
        'staging.security_ticker_history',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.security_ticker_history (
            security_key VARCHAR(32) NOT NULL,
            ticker VARCHAR(32) NOT NULL,
            ticker_valid_from DATE NOT NULL,
            ticker_valid_to_exclusive DATE NOT NULL,
            left_censored BIT NOT NULL,
            right_censored BIT NOT NULL
        );
    END;

    IF OBJECT_ID(
        'staging.index_membership',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.index_membership (
            index_code VARCHAR(20) NOT NULL,
            security_key VARCHAR(32) NOT NULL,
            valid_from DATE NOT NULL,
            valid_to_exclusive DATE NOT NULL,
            left_censored BIT NOT NULL,
            right_censored BIT NOT NULL,
            entry_ticker VARCHAR(32) NOT NULL,
            entry_source_url NVARCHAR(2048) NULL,
            exit_ticker VARCHAR(32) NULL,
            exit_source_url NVARCHAR(2048) NULL
        );
    END;

    IF OBJECT_ID(
        'staging.security_price_eligibility',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.security_price_eligibility (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            effective_price_start DATE NOT NULL,
            effective_price_end_exclusive DATE NOT NULL,
            usable_start DATE NOT NULL,
            usable_end_exclusive DATE NOT NULL,
            standardized_rows INT NOT NULL,
            bridge_rows INT NOT NULL,
            rows_before_usable_window INT NOT NULL,
            rows_after_usable_window INT NOT NULL,
            first_bridge_date DATE NOT NULL,
            last_bridge_date DATE NOT NULL
        );
    END;

    IF OBJECT_ID(
        'staging.daily_security_price',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.daily_security_price (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            price_date DATE NOT NULL,
            [open] DECIMAL(38, 18) NOT NULL,
            high DECIMAL(38, 18) NOT NULL,
            low DECIMAL(38, 18) NOT NULL,
            [close] DECIMAL(38, 18) NOT NULL,
            adjusted_close DECIMAL(38, 18) NOT NULL,
            volume BIGINT NOT NULL,
            dividend DECIMAL(38, 18) NOT NULL,
            split_factor DECIMAL(38, 18) NOT NULL,
            source VARCHAR(64) NOT NULL
        );
    END;

    IF OBJECT_ID(
        'staging.benchmark_series',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.benchmark_series (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            benchmark_name NVARCHAR(100) NOT NULL,
            series_type VARCHAR(32) NOT NULL,
            source VARCHAR(64) NOT NULL
        );
    END;

    IF OBJECT_ID(
        'staging.daily_benchmark_price',
        'U'
    ) IS NULL
    BEGIN
        CREATE TABLE staging.daily_benchmark_price (
            security_key VARCHAR(32) NOT NULL,
            project_ticker VARCHAR(32) NOT NULL,
            provider_symbol VARCHAR(32) NOT NULL,
            price_date DATE NOT NULL,
            [open] DECIMAL(38, 18) NOT NULL,
            high DECIMAL(38, 18) NOT NULL,
            low DECIMAL(38, 18) NOT NULL,
            [close] DECIMAL(38, 18) NOT NULL,
            adjusted_close DECIMAL(38, 18) NOT NULL,
            volume BIGINT NOT NULL,
            dividend DECIMAL(38, 18) NOT NULL,
            split_factor DECIMAL(38, 18) NOT NULL,
            source VARCHAR(64) NOT NULL
        );
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;