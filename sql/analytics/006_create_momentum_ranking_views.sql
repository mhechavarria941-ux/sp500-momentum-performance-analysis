SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

CREATE OR ALTER VIEW
    analytics.v_security_monthly_momentum_ranking
AS
WITH eligible AS (
    SELECT
        feature.analysis_month_number,
        feature.month_start_date,
        feature.month_end_date,
        feature.security_key,
        feature.company_name_reference,
        feature.project_ticker,
        feature.provider_symbol,
        feature.adjusted_close,
        feature.momentum_12_1_start_date,
        feature.momentum_12_1_end_date,
        feature.momentum_12_1,
        feature.momentum_12_1_complete
    FROM analytics.v_security_monthly_return_features
        AS feature
    WHERE feature.momentum_12_1_complete = 1
      AND feature.momentum_12_1 IS NOT NULL
),
ranked AS (
    SELECT
        eligible.*,
        COUNT_BIG(*) OVER (
            PARTITION BY eligible.analysis_month_number
        ) AS eligible_security_count,
        ROW_NUMBER() OVER (
            PARTITION BY eligible.analysis_month_number
            ORDER BY
                eligible.momentum_12_1 DESC,
                eligible.security_key ASC
        ) AS momentum_rank_desc,
        ROW_NUMBER() OVER (
            PARTITION BY eligible.analysis_month_number
            ORDER BY
                eligible.momentum_12_1 ASC,
                eligible.security_key DESC
        ) AS momentum_rank_asc,
        COUNT_BIG(*) OVER (
            PARTITION BY
                eligible.analysis_month_number,
                eligible.momentum_12_1
        ) AS momentum_tie_count,
        ROW_NUMBER() OVER (
            PARTITION BY
                eligible.analysis_month_number,
                eligible.momentum_12_1
            ORDER BY eligible.security_key ASC
        ) AS momentum_tie_break_order,
        NTILE(10) OVER (
            PARTITION BY eligible.analysis_month_number
            ORDER BY
                eligible.momentum_12_1 ASC,
                eligible.security_key DESC
        ) AS momentum_decile
    FROM eligible
)
SELECT
    ranked.analysis_month_number,
    ranked.month_start_date,
    ranked.month_end_date,
    ranked.security_key,
    ranked.company_name_reference,
    ranked.project_ticker,
    ranked.provider_symbol,
    ranked.adjusted_close,
    ranked.momentum_12_1_start_date,
    ranked.momentum_12_1_end_date,
    ranked.momentum_12_1,
    ranked.momentum_12_1_complete,
    ranked.eligible_security_count,
    ranked.momentum_rank_desc,
    ranked.momentum_rank_asc,
    ranked.momentum_tie_count,
    ranked.momentum_tie_break_order,
    ranked.momentum_decile
FROM ranked;
GO

CREATE OR ALTER VIEW
    analytics.v_security_monthly_momentum_portfolio
AS
SELECT
    ranking.analysis_month_number,
    ranking.month_start_date,
    ranking.month_end_date,
    ranking.security_key,
    ranking.company_name_reference,
    ranking.project_ticker,
    ranking.provider_symbol,
    ranking.adjusted_close,
    ranking.momentum_12_1_start_date,
    ranking.momentum_12_1_end_date,
    ranking.momentum_12_1,
    ranking.momentum_12_1_complete,
    ranking.eligible_security_count,
    ranking.momentum_rank_desc,
    ranking.momentum_rank_asc,
    ranking.momentum_tie_count,
    ranking.momentum_tie_break_order,
    ranking.momentum_decile,
    CAST(
        CASE ranking.momentum_decile
            WHEN 1 THEN 'LOSER'
            WHEN 10 THEN 'WINNER'
            ELSE 'MIDDLE'
        END
        AS varchar(16)
    ) AS momentum_portfolio,
    COUNT_BIG(*) OVER (
        PARTITION BY
            ranking.analysis_month_number,
            ranking.momentum_decile
    ) AS decile_security_count,
    CAST(
        1.0
        / CAST(
            COUNT_BIG(*) OVER (
                PARTITION BY
                    ranking.analysis_month_number,
                    ranking.momentum_decile
            )
            AS decimal(38, 18)
        )
        AS decimal(38, 18)
    ) AS equal_weight
FROM analytics.v_security_monthly_momentum_ranking
    AS ranking;
GO

CREATE OR ALTER VIEW
    analytics.v_momentum_decile_monthly_summary
AS
SELECT
    portfolio.analysis_month_number,
    portfolio.month_start_date,
    portfolio.month_end_date,
    portfolio.momentum_decile,
    portfolio.momentum_portfolio,
    MAX(portfolio.eligible_security_count)
        AS eligible_security_count,
    COUNT_BIG(*) AS decile_security_count,
    MIN(portfolio.momentum_12_1)
        AS minimum_momentum_12_1,
    MAX(portfolio.momentum_12_1)
        AS maximum_momentum_12_1,
    AVG(portfolio.momentum_12_1)
        AS average_momentum_12_1,
    SUM(portfolio.equal_weight)
        AS equal_weight_sum
FROM analytics.v_security_monthly_momentum_portfolio
    AS portfolio
GROUP BY
    portfolio.analysis_month_number,
    portfolio.month_start_date,
    portfolio.month_end_date,
    portfolio.momentum_decile,
    portfolio.momentum_portfolio;
GO