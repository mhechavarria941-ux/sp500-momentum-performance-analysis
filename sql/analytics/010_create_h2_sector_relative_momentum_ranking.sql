/*
010_create_h2_sector_relative_momentum_ranking.sql

Purpose
-------
Create the H2 sector-relative momentum ranking layer without joining any
forward-return or performance information.

The local point-in-time GICS security-month file is loaded by the companion
Python application into analytics.security_month_end_gics_sector.

The H2 signal remains the already validated corrected 12-1 momentum feature
from analytics.v_security_monthly_return_features.

Preregistered portfolio formation:
    - rank independently within (analysis_month_number, gics_sector)
    - ORDER BY momentum_12_1 ASC, security_key ASC
    - NTILE(5)
    - Q1 = LOSER
    - Q5 = WINNER
    - equal weight within each sector/quintile sleeve
    - each sector receives 1/11 of an aggregate sector-neutral leg

No forward-return, benchmark-performance, risk, or cost object is referenced.
No core table is modified.

Implementation note: sector-neutral weights use explicit FLOAT division for exact 1/11 sector influence.
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF OBJECT_ID(
    N'analytics.security_month_end_gics_sector',
    N'U'
) IS NULL
BEGIN
    CREATE TABLE analytics.security_month_end_gics_sector
    (
        analysis_month_number INT NOT NULL,
        month_end_date DATE NOT NULL,
        security_key NVARCHAR(64) NOT NULL,
        project_ticker NVARCHAR(32) NOT NULL,
        gics_sector NVARCHAR(64) NOT NULL,

        CONSTRAINT PK_security_month_end_gics_sector
            PRIMARY KEY CLUSTERED
            (
                analysis_month_number,
                security_key
            ),

        CONSTRAINT UQ_security_month_end_gics_sector_date
            UNIQUE
            (
                month_end_date,
                security_key
            ),

        CONSTRAINT CK_security_month_end_gics_sector_month
            CHECK (
                analysis_month_number BETWEEN 1 AND 60
            ),

        CONSTRAINT CK_security_month_end_gics_sector_value
            CHECK (
                gics_sector IN
                (
                    N'Communication Services',
                    N'Consumer Discretionary',
                    N'Consumer Staples',
                    N'Energy',
                    N'Financials',
                    N'Health Care',
                    N'Industrials',
                    N'Information Technology',
                    N'Materials',
                    N'Real Estate',
                    N'Utilities'
                )
            )
    );

    CREATE INDEX IX_security_month_end_gics_sector_sector_month
        ON analytics.security_month_end_gics_sector
        (
            analysis_month_number,
            gics_sector,
            security_key
        )
        INCLUDE
        (
            month_end_date,
            project_ticker
        );
END;
GO

CREATE OR ALTER VIEW analytics.v_security_monthly_sector_momentum_ranking
AS
SELECT
    feature.analysis_month_number,
    DATEFROMPARTS(
        YEAR(feature.month_end_date),
        MONTH(feature.month_end_date),
        1
    ) AS month_start_date,
    feature.month_end_date,
    feature.security_key,
    feature.project_ticker,
    sector.gics_sector,
    feature.momentum_12_1_start_date,
    feature.momentum_12_1_end_date,
    feature.momentum_12_1,

    COUNT_BIG(*) OVER
    (
        PARTITION BY
            feature.analysis_month_number,
            sector.gics_sector
    ) AS sector_eligible_count,

    ROW_NUMBER() OVER
    (
        PARTITION BY
            feature.analysis_month_number,
            sector.gics_sector
        ORDER BY
            feature.momentum_12_1 ASC,
            feature.security_key ASC
    ) AS sector_momentum_rank_asc,

    NTILE(5) OVER
    (
        PARTITION BY
            feature.analysis_month_number,
            sector.gics_sector
        ORDER BY
            feature.momentum_12_1 ASC,
            feature.security_key ASC
    ) AS sector_momentum_quintile

FROM analytics.v_security_monthly_return_features
    AS feature
INNER JOIN analytics.security_month_end_gics_sector
    AS sector
  ON sector.analysis_month_number
   = feature.analysis_month_number
 AND sector.month_end_date
   = feature.month_end_date
 AND sector.security_key
   = feature.security_key
 AND sector.project_ticker
   = feature.project_ticker
WHERE feature.momentum_12_1_complete = 1
  AND feature.momentum_12_1 IS NOT NULL;
GO

CREATE OR ALTER VIEW analytics.v_security_monthly_sector_momentum_portfolio
AS
WITH ranked AS
(
    SELECT
        ranking.*,

        COUNT_BIG(*) OVER
        (
            PARTITION BY
                ranking.analysis_month_number,
                ranking.gics_sector,
                ranking.sector_momentum_quintile
        ) AS sector_quintile_security_count
    FROM analytics.v_security_monthly_sector_momentum_ranking
        AS ranking
)
SELECT
    ranked.analysis_month_number,
    ranked.month_start_date,
    ranked.month_end_date,
    ranked.security_key,
    ranked.project_ticker,
    ranked.gics_sector,
    ranked.momentum_12_1_start_date,
    ranked.momentum_12_1_end_date,
    ranked.momentum_12_1,
    ranked.sector_eligible_count,
    ranked.sector_momentum_rank_asc,
    ranked.sector_momentum_quintile,

    CASE
        WHEN ranked.sector_momentum_quintile = 1
            THEN N'LOSER'
        WHEN ranked.sector_momentum_quintile = 5
            THEN N'WINNER'
        ELSE N'MIDDLE'
    END AS sector_momentum_portfolio,

    ranked.sector_quintile_security_count,

    1.0
    / NULLIF(
        CAST(
            ranked.sector_quintile_security_count
            AS FLOAT
        ),
        0.0
    ) AS sector_equal_weight,

    (
        CAST(1.0 AS FLOAT)
        / CAST(11.0 AS FLOAT)
    )
    * (
        CAST(1.0 AS FLOAT)
        / NULLIF(
            CAST(
                ranked.sector_quintile_security_count
                AS FLOAT
            ),
            CAST(0.0 AS FLOAT)
        )
    ) AS sector_neutral_leg_weight

FROM ranked;
GO

CREATE OR ALTER VIEW analytics.v_sector_momentum_quintile_monthly_summary
AS
SELECT
    portfolio.analysis_month_number,
    portfolio.month_start_date,
    portfolio.month_end_date,
    portfolio.gics_sector,
    portfolio.sector_momentum_quintile,
    portfolio.sector_momentum_portfolio,

    COUNT_BIG(*) AS security_count,

    MIN(portfolio.momentum_12_1)
        AS minimum_momentum_12_1,

    AVG(portfolio.momentum_12_1)
        AS average_momentum_12_1,

    MAX(portfolio.momentum_12_1)
        AS maximum_momentum_12_1,

    SUM(portfolio.sector_equal_weight)
        AS sector_weight_sum,

    SUM(portfolio.sector_neutral_leg_weight)
        AS sector_neutral_leg_weight_sum

FROM analytics.v_security_monthly_sector_momentum_portfolio
    AS portfolio
GROUP BY
    portfolio.analysis_month_number,
    portfolio.month_start_date,
    portfolio.month_end_date,
    portfolio.gics_sector,
    portfolio.sector_momentum_quintile,
    portfolio.sector_momentum_portfolio;
GO
