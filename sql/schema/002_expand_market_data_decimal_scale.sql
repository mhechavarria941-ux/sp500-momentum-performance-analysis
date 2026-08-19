SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(
        'core.daily_security_price',
        'U'
    ) IS NULL
        OR OBJECT_ID(
            'core.daily_benchmark_price',
            'U'
        ) IS NULL
        OR OBJECT_ID(
            'staging.daily_security_price',
            'U'
        ) IS NULL
        OR OBJECT_ID(
            'staging.daily_benchmark_price',
            'U'
        ) IS NULL
    BEGIN
        THROW 50001,
            'Required market-data tables are missing.',
            1;
    END;

    DECLARE @needs_migration BIT = 0;

    IF EXISTS (
        SELECT
            1
        FROM sys.columns AS c
        JOIN sys.tables AS t
            ON t.object_id = c.object_id
        JOIN sys.schemas AS s
            ON s.schema_id = t.schema_id
        WHERE
            s.name IN (
                'core',
                'staging'
            )
            AND t.name IN (
                'daily_security_price',
                'daily_benchmark_price'
            )
            AND c.name IN (
                'open',
                'high',
                'low',
                'close',
                'adjusted_close',
                'dividend',
                'split_factor'
            )
            AND (
                c.precision <> 38
                OR c.scale <> 18
            )
    )
    BEGIN
        SET @needs_migration = 1;
    END;

    IF @needs_migration = 1
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM core.daily_security_price
        )
        OR EXISTS (
            SELECT 1
            FROM core.daily_benchmark_price
        )
        OR EXISTS (
            SELECT 1
            FROM staging.daily_security_price
        )
        OR EXISTS (
            SELECT 1
            FROM staging.daily_benchmark_price
        )
        BEGIN
            THROW 50002,
                'Decimal-scale migration requires empty price tables.',
                1;
        END;

        IF EXISTS (
            SELECT
                1
            FROM sys.indexes
            WHERE
                object_id = OBJECT_ID(
                    'core.daily_security_price'
                )
                AND name =
                    'IX_daily_security_price_security_date'
        )
        BEGIN
            DROP INDEX
                IX_daily_security_price_security_date
            ON core.daily_security_price;
        END;

        IF OBJECT_ID(
            'core.CK_daily_security_price_positive',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_security_price
            DROP CONSTRAINT
                CK_daily_security_price_positive;

        IF OBJECT_ID(
            'core.CK_daily_security_price_high',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_security_price
            DROP CONSTRAINT
                CK_daily_security_price_high;

        IF OBJECT_ID(
            'core.CK_daily_security_price_low',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_security_price
            DROP CONSTRAINT
                CK_daily_security_price_low;

        IF OBJECT_ID(
            'core.CK_daily_security_price_actions',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_security_price
            DROP CONSTRAINT
                CK_daily_security_price_actions;

        IF OBJECT_ID(
            'core.CK_daily_benchmark_price_positive',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_benchmark_price
            DROP CONSTRAINT
                CK_daily_benchmark_price_positive;

        IF OBJECT_ID(
            'core.CK_daily_benchmark_price_high',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_benchmark_price
            DROP CONSTRAINT
                CK_daily_benchmark_price_high;

        IF OBJECT_ID(
            'core.CK_daily_benchmark_price_low',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_benchmark_price
            DROP CONSTRAINT
                CK_daily_benchmark_price_low;

        IF OBJECT_ID(
            'core.CK_daily_benchmark_price_actions',
            'C'
        ) IS NOT NULL
            ALTER TABLE
                core.daily_benchmark_price
            DROP CONSTRAINT
                CK_daily_benchmark_price_actions;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            [open] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            high DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            low DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            [close] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            adjusted_close DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            dividend DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_security_price
        ALTER COLUMN
            split_factor DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            [open] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            high DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            low DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            [close] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            adjusted_close DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            dividend DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_benchmark_price
        ALTER COLUMN
            split_factor DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            [open] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            high DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            low DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            [close] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            adjusted_close DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            dividend DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_security_price
        ALTER COLUMN
            split_factor DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            [open] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            high DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            low DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            [close] DECIMAL(38, 18) NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            adjusted_close DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            dividend DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            staging.daily_benchmark_price
        ALTER COLUMN
            split_factor DECIMAL(38, 18)
            NOT NULL;

        ALTER TABLE
            core.daily_security_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_security_price_positive
        CHECK (
            [open] > 0
            AND high > 0
            AND low > 0
            AND [close] > 0
            AND adjusted_close > 0
        );

        ALTER TABLE
            core.daily_security_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_security_price_high
        CHECK (
            high >= [open]
            AND high >= low
            AND high >= [close]
        );

        ALTER TABLE
            core.daily_security_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_security_price_low
        CHECK (
            low <= [open]
            AND low <= high
            AND low <= [close]
        );

        ALTER TABLE
            core.daily_security_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_security_price_actions
        CHECK (
            volume >= 0
            AND dividend >= 0
            AND split_factor > 0
        );

        ALTER TABLE
            core.daily_benchmark_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_benchmark_price_positive
        CHECK (
            [open] > 0
            AND high > 0
            AND low > 0
            AND [close] > 0
            AND adjusted_close > 0
        );

        ALTER TABLE
            core.daily_benchmark_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_benchmark_price_high
        CHECK (
            high >= [open]
            AND high >= low
            AND high >= [close]
        );

        ALTER TABLE
            core.daily_benchmark_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_benchmark_price_low
        CHECK (
            low <= [open]
            AND low <= high
            AND low <= [close]
        );

        ALTER TABLE
            core.daily_benchmark_price
        WITH CHECK ADD CONSTRAINT
            CK_daily_benchmark_price_actions
        CHECK (
            volume >= 0
            AND dividend >= 0
            AND split_factor > 0
        );
    END;

    IF NOT EXISTS (
        SELECT
            1
        FROM sys.indexes
        WHERE
            object_id = OBJECT_ID(
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

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;